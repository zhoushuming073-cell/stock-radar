"""Resumable, private near-lower candidate retrieval on frozen Train/Validation.

This deliberately leaves the full-state Stage D scanner untouched. A causal
necessary gate avoids expensive range detection only where Stage C's target
state is impossible. Unknown prefixes are sent to the full RI provider.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
import os
from pathlib import Path
from time import perf_counter

import yaml

from radar.box_labeling.fast_gate import VERSION as GATE_VERSION, necessary_near_lower
from radar.box_labeling.history import BoxHistory
from radar.box_labeling.lower_band import LowerBandConfig
from radar.box_labeling.range_detector import RangeConfig
from radar.box_labeling.stage_b import digest, packed
from scripts.audit_box_fast_gate_stage_d import recent_prefixes, safe_prefix
from scripts.scan_box_daily_stage_d import (
    SPLITS, chunks, dates_in_split, indexed_rows, runtime_versions,
    scan_chunk, source_digest, verify_existing,
)

VERSION = "box-near-lower-candidate-stage-d-v1"
TARGET = "NEAR_LOWER_STABILIZING"


def select_candidates(rows: list[dict], prefixes: list[dict],
                      config: LowerBandConfig) -> tuple[list[dict], dict]:
    """Preserve exact eligible ordering and fail if the bulk query drifts."""
    ids = [row["security_id"] for row in rows]
    by_id = {row["security_id"]: row for row in prefixes}
    if len(ids) != len(set(ids)) or len(prefixes) != len(by_id) or set(ids) != set(by_id):
        raise ValueError("recent-prefix query does not match eligible identities")
    selected = []
    reasons = Counter()
    unknown = 0
    for row in rows:
        prefix = by_id[row["security_id"]]
        if not safe_prefix(prefix):
            possible, why = True, ("unknown_recent_prefix",)
        else:
            possible, why = necessary_near_lower(
                prefix["closes"], prefix["lows"], prefix["volumes"], config)
        if possible:
            selected.append(row)
            unknown += "unknown_recent_prefix" in why
        else:
            reasons.update(why)
    return selected, {"eligible": len(rows), "possible": len(selected),
                      "certainly_not": len(rows)-len(selected),
                      "unknown_retained": unknown,
                      "rejection_reasons_overlapping": dict(sorted(reasons.items()))}


def near_chunk(provider: BoxHistory, day: str, rows: list[dict],
               detector_config: RangeConfig, context_config: LowerBandConfig) -> dict:
    scanned = scan_chunk(provider, day, rows, detector_config, context_config)
    near = []
    for row in scanned["contexts"]:
        detectors = {name: context for name, context in row["detectors"].items()
                     if context["state"] == TARGET}
        if detectors:
            near.append({**row, "detectors": detectors})
    return {"requested": scanned["requested"],
            "processed": scanned["processed"],
            "excluded": scanned["excluded"], "near_contexts": near}


def _code_hashes() -> dict[str, str]:
    root = Path(__file__).resolve().parents[1]
    return {name: source_digest(root / path) for name, path in {
        "candidate_scanner": "scripts/scan_box_near_lower_stage_d.py",
        "gate": "src/radar/box_labeling/fast_gate.py",
        "prefix_query": "scripts/audit_box_fast_gate_stage_d.py",
        "daily_scanner": "scripts/scan_box_daily_stage_d.py",
        "detector": "src/radar/box_labeling/range_detector.py",
        "context": "src/radar/box_labeling/lower_band.py",
        "history": "src/radar/box_labeling/history.py",
        "canonical": "src/radar/pit/shape.py",
        "receipt": "src/radar/box_labeling/stage_b.py",
    }.items()}


def _selection(provider: BoxHistory, day: str, config: LowerBandConfig):
    rows, denominator = indexed_rows(provider.api.core.connection, day)
    prefixes = recent_prefixes(provider.api.core.connection, day)
    selected, gate = select_candidates(rows, prefixes, config)
    if gate["eligible"] != denominator["eligible"]:
        raise ValueError("eligible denominator drift")
    return selected, denominator, gate


def _expected(split: str, day: str, index: int, groups: list[list[dict]],
              group: list[dict], chunk_size: int, denominator: dict,
              gate: dict, semantic_hash: str, detector_config: RangeConfig,
              context_config: LowerBandConfig, code_hashes: dict,
              versions: dict) -> dict:
    return {"version": VERSION, "gate_version": GATE_VERSION,
            "split": split, "decision_date": day, "chunk_index": index,
            "chunk_count": len(groups), "chunk_size": chunk_size,
            "selection_sha256": digest(packed(group)),
            "gate_receipt_sha256": digest(packed(gate)),
            "denominator": denominator, "gate": gate,
            "ri_semantic_hash": semantic_hash,
            "detector_config_hash": detector_config.digest,
            "context_config_hash": context_config.digest,
            "code_hashes": code_hashes, "runtime_versions": versions,
            "identity_gate": "PROVISIONAL_OBSERVATIONAL",
            "future_outcomes_read": False, "formal_signal_stream": False}


def _check_payload(payload: dict, group: list[dict]) -> None:
    ids = {row["security_id"] for row in group}
    excluded = [row["security_id"] for row in payload["excluded"]]
    near = payload["near_contexts"]
    near_ids = [row["security_id"] for row in near]
    if (payload["requested"] != len(group)
            or payload["processed"] + len(excluded) != len(group)
            or len(excluded) != len(set(excluded))
            or len(near_ids) != len(set(near_ids))
            or set(excluded) & set(near_ids)
            or not set(excluded + near_ids) <= ids):
        raise ValueError("candidate chunk count or identity drift")
    for row in near:
        if not row["detectors"] or any(
            context["state"] != TARGET
            or context["detector"] != name
            or context["decision_date"] != payload["decision_date"]
            or context["config_hash"] != payload["context_config_hash"]
            or context["detector_config_hash"] != payload["detector_config_hash"]
            for name, context in row["detectors"].items()):
            raise ValueError("candidate context provenance/state drift")


def execute(research_root: Path, split: str, start: str, end: str,
            output_dir: Path, detector_config_path: Path,
            context_config_path: Path, chunk_size: int = 256,
            max_new_chunks: int | None = None, verify_only: bool = False) -> dict:
    if max_new_chunks is not None and max_new_chunks < 1:
        raise ValueError("max_new_chunks must be positive")
    root, output = research_root.resolve(), output_dir.resolve()
    if not output.is_relative_to(root / "data"):
        raise ValueError("private output must stay under research-root/data")
    detector_config = RangeConfig.from_mapping(yaml.safe_load(detector_config_path.read_bytes()))
    context_config = LowerBandConfig.from_mapping(yaml.safe_load(context_config_path.read_bytes()))
    hashes, versions = _code_hashes(), runtime_versions()
    summary = {"version": VERSION, "split": split, "start": start, "end": end,
               "verify_only": verify_only, "new_chunks": 0,
               "verified_chunks": 0, "missing_chunks": 0,
               "sessions": 0, "eligible_security_days": 0,
               "possible_security_days": 0, "certainly_not_security_days": 0,
               "unknown_retained": 0, "provider_exclusions": 0,
               "near_lower_union_rows": 0, "new_compute_seconds": 0.0,
               "complete": False, "future_outcomes_read": False,
               "formal_signal_stream": False}
    file_hashes = []
    with BoxHistory(root) as provider:
        if provider.api.profile["semantics"]["frozen_splits"].get(split) != list(SPLITS.get(split, ())):
            raise ValueError("frozen split contract drift")
        days = dates_in_split(provider.api.core.connection, split, start, end)
        if not days:
            raise ValueError("selected interval has no frozen sessions")
        summary["sessions"] = len(days)
        summary["ri_semantic_hash"] = provider.semantic_hash
        summary["config_hashes"] = {"detector": detector_config.digest,
                                    "context": context_config.digest}
        summary["code_hashes"] = hashes
        summary["runtime_versions"] = versions
        stop = False
        for day in days:
            selected, denominator, gate = _selection(provider, day, context_config)
            summary["eligible_security_days"] += gate["eligible"]
            summary["possible_security_days"] += gate["possible"]
            summary["certainly_not_security_days"] += gate["certainly_not"]
            summary["unknown_retained"] += gate["unknown_retained"]
            groups = chunks(selected, chunk_size)
            folder = output / split / day
            expected_names = {f"{i:04d}-of-{len(groups):04d}.json"
                              for i in range(len(groups))}
            if verify_only:
                actual = {p.name for p in folder.glob("*.json")}
                if actual - expected_names or any(folder.glob("*.partial")):
                    raise ValueError("unexpected or partial candidate artifact")
            for index, group in enumerate(groups):
                expected = _expected(split, day, index, groups, group, chunk_size,
                                     denominator, gate, provider.semantic_hash,
                                     detector_config, context_config, hashes, versions)
                path = folder / f"{index:04d}-of-{len(groups):04d}.json"
                if path.exists():
                    payload = verify_existing(path, expected)
                    _check_payload(payload, group)
                    summary["verified_chunks"] += 1
                    file_hashes.append(sha256(path.read_bytes()).hexdigest())
                elif verify_only:
                    summary["missing_chunks"] += 1
                    continue
                else:
                    if max_new_chunks is not None and summary["new_chunks"] >= max_new_chunks:
                        stop = True
                        break
                    began = perf_counter()
                    payload = {**expected, **near_chunk(provider, day, group,
                        detector_config, context_config)}
                    _check_payload(payload, group)
                    summary["new_compute_seconds"] += perf_counter()-began
                    raw = packed({"payload": payload,
                                  "payload_sha256": digest(packed(payload))})
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix(".partial")
                    with temporary.open("xb") as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, path)
                    summary["new_chunks"] += 1
                    file_hashes.append(sha256(raw).hexdigest())
                summary["provider_exclusions"] += len(payload["excluded"])
                summary["near_lower_union_rows"] += len(payload["near_contexts"])
            if stop:
                break
    summary["complete"] = not stop and summary["missing_chunks"] == 0
    summary["new_compute_seconds"] = round(summary["new_compute_seconds"], 3)
    summary["verified_file_set_sha256"] = (
        digest(packed(file_hashes)) if summary["complete"] else None)
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--split", choices=tuple(SPLITS), required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--detector-config", type=Path,
                        default=Path("config/box_range_detector_stage_a_v1.yaml"))
    parser.add_argument("--context-config", type=Path,
                        default=Path("config/box_lower_band_context_v1.yaml"))
    parser.add_argument("--chunk-size", type=int, default=256)
    parser.add_argument("--max-new-chunks", type=int)
    parser.add_argument("--verify-only", action="store_true")
    args = parser.parse_args()
    print(json.dumps(execute(args.research_root, args.split, args.start,
                             args.end, args.output_dir, args.detector_config,
                             args.context_config, args.chunk_size,
                             args.max_new_chunks, args.verify_only),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

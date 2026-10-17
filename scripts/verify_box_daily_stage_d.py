"""Verify complete private daily chunks; print aggregate evidence only."""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import yaml

from radar.box_labeling.history import BoxHistory
from radar.box_labeling.lower_band import LowerBandConfig
from radar.box_labeling.range_detector import RangeConfig
from radar.box_labeling.stage_b import packed
from scripts.scan_box_daily_stage_d import (
    VERSION, SPLITS, chunks, dates_in_split, indexed_rows, source_digest,
    runtime_versions, verify_existing,
)

DETECTORS = ("quantile-zone-v1", "confirmed-pivot-zone-v1")


def reject_unexpected_chunks(folder: Path, expected_names: set[str]) -> None:
    existing_names = {path.name for path in folder.glob("*.json")}
    if existing_names - expected_names or any(folder.glob("*.partial")):
        raise ValueError("unexpected or partial daily chunk artifact")


def check_payload(payload: dict, group: list[dict]) -> None:
    selected = {row["security_id"] for row in group}
    excluded = payload["excluded"]
    contexts = payload["contexts"]
    if payload["requested"] != len(group) or payload["processed"] + len(excluded) != len(group):
        raise ValueError("chunk requested/processed/excluded counts do not reconcile")
    excluded_ids = [row["security_id"] for row in excluded]
    context_ids = [row["security_id"] for row in contexts]
    if (len(excluded_ids) != len(set(excluded_ids)) or
            len(context_ids) != len(set(context_ids)) or
            set(excluded_ids) & set(context_ids) or
            not set(excluded_ids + context_ids) <= selected):
        raise ValueError("chunk context/exclusion identity mapping is invalid")
    if set(payload["states"]) != set(DETECTORS) or set(payload["statuses"]) != set(DETECTORS):
        raise ValueError("detector result missing or mixed")
    for name in DETECTORS:
        if sum(payload["states"][name].values()) != payload["processed"]:
            raise ValueError("lower-band state count does not reconcile")
        if sum(payload["statuses"][name].values()) != payload["processed"]:
            raise ValueError("range-detector status count does not reconcile")
        observed = Counter(row["detectors"][name]["state"]
                           for row in contexts if name in row["detectors"])
        expected = Counter({state: count for state, count in payload["states"][name].items()
                            if state != "NO_ACTIVE_RANGE" and count})
        if observed != expected:
            raise ValueError("active context rows do not reconcile with detector states")
    for row in contexts:
        if not row["detectors"] or set(row["detectors"]) - set(DETECTORS):
            raise ValueError("context row has unknown detector")
        for name, context in row["detectors"].items():
            if (context["detector"] != name or context["state"] == "NO_ACTIVE_RANGE" or
                    context["decision_date"] != payload["decision_date"] or
                    context["config_hash"] != payload["context_config_hash"] or
                    context["detector_config_hash"] != payload["detector_config_hash"]):
                raise ValueError("context row provenance/state mismatch")


def verify(research_root: Path, split: str, start: str, end: str, output_dir: Path,
           detector_config_path: Path, context_config_path: Path,
           chunk_size: int = 256) -> dict:
    root = research_root.resolve()
    output = output_dir.resolve()
    if not output.is_relative_to(root / "data"):
        raise ValueError("private scan output must stay under research-root/data")
    detector_config = RangeConfig.from_mapping(yaml.safe_load(detector_config_path.read_bytes()))
    context_config = LowerBandConfig.from_mapping(yaml.safe_load(context_config_path.read_bytes()))
    here = Path(__file__).resolve().parents[1]
    code_hashes = {"scanner": source_digest(here / "scripts/scan_box_daily_stage_d.py"),
                   "detector": source_digest(here / "src/radar/box_labeling/range_detector.py"),
                   "context": source_digest(here / "src/radar/box_labeling/lower_band.py"),
                   "history": source_digest(here / "src/radar/box_labeling/history.py"),
                   "canonical": source_digest(here / "src/radar/pit/shape.py"),
                   "receipt": source_digest(here / "src/radar/box_labeling/stage_b.py")}
    versions = runtime_versions()
    totals = {"version": VERSION, "split": split, "start": start, "end": end,
              "verifier_sha256": source_digest(Path(__file__)),
              "ri_semantic_hash": None,
              "detector_config_hash": detector_config.digest,
              "context_config_hash": context_config.digest,
              "code_hashes": code_hashes, "runtime_versions": versions,
              "days": 0, "expected_chunks": 0, "verified_chunks": 0,
              "missing_chunks": 0, "indexed_security_days": 0,
              "eligible_security_days": 0, "processed_security_days": 0,
              "provider_exclusions": 0, "context_rows": 0,
              "near_lower_union_rows": 0, "near_lower_both_rows": 0,
              "states": {name: Counter() for name in DETECTORS},
              "statuses": {name: Counter() for name in DETECTORS},
              "future_outcomes_read": False, "formal_signal_stream": False}
    hashes = []
    with BoxHistory(root) as provider:
        totals["ri_semantic_hash"] = provider.semantic_hash
        if provider.api.profile["semantics"]["frozen_splits"].get(split) != list(SPLITS.get(split, ())):
            raise ValueError("frozen split contract drift")
        days = dates_in_split(provider.api.core.connection, split, start, end)
        if not days:
            raise ValueError("selected interval has no frozen trading sessions")
        totals["days"] = len(days)
        for day in days:
            rows, denominator = indexed_rows(provider.api.core.connection, day)
            totals["indexed_security_days"] += denominator["indexed"]
            totals["eligible_security_days"] += denominator["eligible"]
            groups = chunks(rows, chunk_size)
            totals["expected_chunks"] += len(groups)
            folder = output / split / day
            expected_names = {f"{i:04d}-of-{len(groups):04d}.json"
                              for i in range(len(groups))}
            reject_unexpected_chunks(folder, expected_names)
            for index, group in enumerate(groups):
                path = output / split / day / f"{index:04d}-of-{len(groups):04d}.json"
                if not path.exists():
                    totals["missing_chunks"] += 1
                    continue
                expected = {"version": VERSION, "split": split, "decision_date": day,
                            "chunk_index": index, "chunk_count": len(groups),
                            "chunk_size": chunk_size,
                            "selection_sha256": sha256(packed(group)).hexdigest(),
                            "denominator": denominator,
                            "ri_semantic_hash": provider.semantic_hash,
                            "detector_config_hash": detector_config.digest,
                            "context_config_hash": context_config.digest,
                            "code_hashes": code_hashes,
                            "runtime_versions": versions,
                            "identity_gate": "PROVISIONAL_OBSERVATIONAL",
                            "future_outcomes_read": False,
                            "formal_signal_stream": False}
                payload = verify_existing(path, expected)
                check_payload(payload, group)
                hashes.append(sha256(path.read_bytes()).hexdigest())
                totals["verified_chunks"] += 1
                totals["processed_security_days"] += payload["processed"]
                totals["provider_exclusions"] += len(payload["excluded"])
                totals["context_rows"] += len(payload["contexts"])
                for row in payload["contexts"]:
                    near_count = sum(context["state"] == "NEAR_LOWER_STABILIZING"
                                     for context in row["detectors"].values())
                    totals["near_lower_union_rows"] += near_count > 0
                    totals["near_lower_both_rows"] += near_count == len(DETECTORS)
                for name in DETECTORS:
                    totals["states"][name].update(payload["states"][name])
                    totals["statuses"][name].update(payload["statuses"][name])
    totals["complete"] = totals["missing_chunks"] == 0
    if totals["complete"] and totals["processed_security_days"] + totals["provider_exclusions"] != totals["eligible_security_days"]:
        raise ValueError("full eligible denominator does not reconcile")
    totals["verified_file_set_sha256"] = sha256(packed(hashes)).hexdigest()
    totals["states"] = {name: dict(sorted(value.items())) for name, value in totals["states"].items()}
    totals["statuses"] = {name: dict(sorted(value.items())) for name, value in totals["statuses"].items()}
    return totals


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--research-root", type=Path, required=True)
    p.add_argument("--split", choices=tuple(SPLITS), required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--detector-config", type=Path,
                   default=Path("config/box_range_detector_stage_a_v1.yaml"))
    p.add_argument("--context-config", type=Path,
                   default=Path("config/box_lower_band_context_v1.yaml"))
    p.add_argument("--chunk-size", type=int, default=256)
    a = p.parse_args()
    print(json.dumps(verify(a.research_root, a.split, a.start, a.end,
                            a.output_dir, a.detector_config, a.context_config,
                            a.chunk_size), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

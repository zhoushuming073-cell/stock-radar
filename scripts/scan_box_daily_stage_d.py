"""Resumable private T-only box-context scan of frozen Train/Validation days.

One immutable file per date/chunk makes interruption safe. This writes no
outcomes, human labels, LEAN signals or public security/date mappings.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
from importlib.metadata import version as package_version
import json
import os
from pathlib import Path
from platform import python_version
from time import perf_counter

import yaml

from radar.box_labeling.history import BoxHistory
from radar.box_labeling.lower_band import LowerBandConfig, assess_lower_band
from radar.box_labeling.range_detector import (
    ConfirmedPivotDetector, QuantileZoneDetector, RangeConfig,
)
from radar.box_labeling.stage_b import digest, packed

VERSION = "box-daily-context-stage-d-v4"
SPLITS = {"train": ("2021-09-01", "2024-08-29"),
          "validation": ("2024-09-30", "2025-09-08")}
RUNTIME_PACKAGES = ("numpy", "pandas", "scipy", "duckdb", "PyYAML")


def source_digest(path: Path) -> str:
    return sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def runtime_versions() -> dict[str, str]:
    return {"python": python_version(),
            **{name: package_version(name) for name in RUNTIME_PACKAGES}}


def dates_in_split(connection, split: str, start: str, end: str) -> list[str]:
    if split not in SPLITS or not SPLITS[split][0] <= start <= end <= SPLITS[split][1]:
        raise ValueError("scan dates must remain inside one frozen Train/Validation split")
    return [str(row[0]) for row in connection.execute(
        "SELECT date FROM sessions WHERE date BETWEEN ? AND ? ORDER BY date",
        [start, end]).fetchall()]


def indexed_rows(connection, day: str) -> tuple[list[dict], dict]:
    counts = connection.execute("""SELECT count(*) AS indexed,
        count(*) FILTER (WHERE supported_membership) AS supported,
        count(*) FILTER (WHERE shape_research_ready) AS ready,
        count(*) FILTER (WHERE supported_membership AND shape_research_ready) AS eligible
        FROM universe_window_index WHERE decision_date=? AND length=126""", [day]).fetchone()
    values = connection.execute("""SELECT security_id,source,basis,membership_status
        FROM universe_window_index WHERE decision_date=? AND length=126
          AND supported_membership AND shape_research_ready
        ORDER BY security_id""", [day]).fetchall()
    if len(values) != counts[3] or len({row[0] for row in values}) != len(values):
        raise ValueError("eligible index count or security identity is ambiguous")
    keys = ("security_id", "source", "basis", "membership_status")
    return [dict(zip(keys, row)) for row in values], dict(zip(
        ("indexed", "supported", "ready", "eligible"), map(int, counts)))


def chunks(rows: list[dict], chunk_size: int) -> list[list[dict]]:
    if not 1 <= chunk_size <= 1024:
        raise ValueError("chunk_size must be 1..1024")
    # An empty eligible day still needs an immutable denominator receipt.
    return [rows[i:i+chunk_size] for i in range(0, len(rows), chunk_size)] or [[]]


def verify_existing(path: Path, expected: dict) -> dict:
    receipt = json.loads(path.read_bytes())
    if set(receipt) != {"payload", "payload_sha256"} or digest(packed(receipt["payload"])) != receipt["payload_sha256"]:
        raise ValueError("existing daily chunk is corrupted")
    payload = receipt["payload"]
    if any(payload.get(key) != value for key, value in expected.items()):
        raise ValueError("existing daily chunk has data/config/code drift")
    return payload


def scan_chunk(provider: BoxHistory, day: str, rows: list[dict],
               detector_config: RangeConfig, context_config: LowerBandConfig) -> dict:
    detectors = (QuantileZoneDetector(), ConfirmedPivotDetector())
    states = {detector.name: Counter() for detector in detectors}
    statuses = {detector.name: Counter() for detector in detectors}
    excluded = []
    contexts = []
    for row in rows:
        try:
            history = provider.history(row["security_id"], day, 126)
        except ValueError as exc:
            excluded.append({"security_id": row["security_id"],
                             "reason": type(exc).__name__ + ": " + str(exc)})
            continue
        if (history.attrs["source"] != row["source"] or
                history.attrs["basis"] != row["basis"]):
            raise ValueError("index/history source or basis drift")
        found = {}
        for detector in detectors:
            scan = detector.detect(history, day, detector_config)
            context = assess_lower_band(scan, history, detector_config, context_config)
            states[detector.name][context.state] += 1
            statuses[detector.name][scan.status_at_t] += 1
            if context.state != "NO_ACTIVE_RANGE":
                found[detector.name] = asdict(context)
        if found:
            contexts.append({"security_id": row["security_id"],
                             "source": row["source"], "basis": row["basis"],
                             "membership_status": row["membership_status"],
                             "detectors": found})
    return {"requested": len(rows), "processed": len(rows)-len(excluded),
            "excluded": excluded, "contexts": contexts,
            "states": {key: dict(sorted(value.items())) for key, value in states.items()},
            "statuses": {key: dict(sorted(value.items())) for key, value in statuses.items()}}


def run(research_root: Path, split: str, start: str, end: str,
        output_dir: Path, detector_config_path: Path, context_config_path: Path,
        chunk_size: int = 256, max_new_chunks: int | None = None) -> dict:
    if max_new_chunks is not None and max_new_chunks < 1:
        raise ValueError("max_new_chunks must be positive")
    root = research_root.resolve()
    output = output_dir.resolve()
    if not output.is_relative_to(root / "data"):
        raise ValueError("private scan output must stay under research-root/data")
    detector_config = RangeConfig.from_mapping(yaml.safe_load(detector_config_path.read_bytes()))
    context_config = LowerBandConfig.from_mapping(yaml.safe_load(context_config_path.read_bytes()))
    code_hashes = {"scanner": source_digest(Path(__file__)),
                   "detector": source_digest(Path(__file__).resolve().parents[1] /
                                             "src/radar/box_labeling/range_detector.py"),
                   "context": source_digest(Path(__file__).resolve().parents[1] /
                                            "src/radar/box_labeling/lower_band.py"),
                   "history": source_digest(Path(__file__).resolve().parents[1] /
                                            "src/radar/box_labeling/history.py"),
                   "canonical": source_digest(Path(__file__).resolve().parents[1] /
                                              "src/radar/pit/shape.py"),
                   "receipt": source_digest(Path(__file__).resolve().parents[1] /
                                            "src/radar/box_labeling/stage_b.py")}
    versions = runtime_versions()
    result = {"version": VERSION, "split": split, "start": start, "end": end,
              "new_chunks": 0, "verified_existing_chunks": 0, "processed_security_days": 0,
              "indexed_security_days": 0, "eligible_security_days": 0,
              "provider_exclusions": 0, "candidate_context_rows": 0, "complete": False,
              "new_compute_seconds": 0.0,
              "future_outcomes_read": False, "formal_signal_stream": False}
    with BoxHistory(root) as provider:
        if provider.api.profile["semantics"]["frozen_splits"].get(split) != list(SPLITS.get(split, ())):
            raise ValueError("frozen split contract drift")
        days = dates_in_split(provider.api.core.connection, split, start, end)
        if not days:
            raise ValueError("selected interval has no frozen trading sessions")
        result["sessions"] = len(days)
        result["ri_semantic_hash"] = provider.semantic_hash
        result["config_hashes"] = {"detector": detector_config.digest,
                                   "context": context_config.digest}
        result["code_hashes"] = code_hashes
        result["runtime_versions"] = versions
        stop = False
        for day in days:
            rows, denominator = indexed_rows(provider.api.core.connection, day)
            result["indexed_security_days"] += denominator["indexed"]
            result["eligible_security_days"] += denominator["eligible"]
            groups = chunks(rows, chunk_size)
            for index, group in enumerate(groups):
                expected = {"version": VERSION, "split": split, "decision_date": day,
                            "chunk_index": index, "chunk_count": len(groups),
                            "chunk_size": chunk_size,
                            "selection_sha256": digest(packed(group)),
                            "denominator": denominator,
                            "ri_semantic_hash": provider.semantic_hash,
                            "detector_config_hash": detector_config.digest,
                            "context_config_hash": context_config.digest,
                            "code_hashes": code_hashes,
                            "runtime_versions": versions,
                            "identity_gate": "PROVISIONAL_OBSERVATIONAL",
                            "future_outcomes_read": False,
                            "formal_signal_stream": False}
                path = output / split / day / f"{index:04d}-of-{len(groups):04d}.json"
                if path.exists():
                    payload = verify_existing(path, expected)
                    result["verified_existing_chunks"] += 1
                else:
                    if max_new_chunks is not None and result["new_chunks"] >= max_new_chunks:
                        stop = True
                        break
                    began = perf_counter()
                    payload = {**expected, **scan_chunk(provider, day, group,
                        detector_config, context_config)}
                    result["new_compute_seconds"] += perf_counter() - began
                    raw = packed({"payload": payload,
                                  "payload_sha256": digest(packed(payload))})
                    path.parent.mkdir(parents=True, exist_ok=True)
                    temporary = path.with_suffix(".partial")
                    with temporary.open("xb") as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                    os.replace(temporary, path)
                    result["new_chunks"] += 1
                result["processed_security_days"] += payload["processed"]
                result["provider_exclusions"] += len(payload["excluded"])
                result["candidate_context_rows"] += len(payload["contexts"])
            if stop:
                break
    result["complete"] = not stop
    result["new_compute_seconds"] = round(result["new_compute_seconds"], 3)
    return result


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
    p.add_argument("--max-new-chunks", type=int)
    a = p.parse_args()
    print(json.dumps(run(a.research_root, a.split, a.start, a.end, a.output_dir,
                         a.detector_config, a.context_config, a.chunk_size,
                         a.max_new_chunks), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

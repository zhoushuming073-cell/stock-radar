"""T-only accepted raw-price overlap for a sealed candidate prefix.

This independently verifies the immutable candidate files before comparing
decision-close OHLCV. It never queries dates after each candidate's T day.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import duckdb

from radar.box_labeling.history import BoxHistory
from radar.box_labeling.stage_b import digest, packed
from scripts.audit_box_candidate_execution_metadata import candidate_requests
from scripts.audit_box_candidate_source_basis import audit as source_audit
from scripts.audit_box_candidate_tday_price_bridge import (
    DOLT_SOURCE, _file_sha256, accepted_database, compare_tday,
)
from scripts.scan_box_daily_stage_d import SPLITS

VERSION = "box-candidate-prefix-tday-v1"


def classify_requests(requests: list[dict], shape_connection,
                      accepted_connection, decision_date: str) -> Counter[str]:
    counts: Counter[str] = Counter()
    for request in requests:
        if request["decision_date"] != decision_date:
            raise ValueError("candidate decision-date drift")
        if request["source"] == DOLT_SOURCE and request["basis"] == "raw":
            counts[compare_tday(shape_connection, accepted_connection,
                                request["security_id"], decision_date)] += 1
    return counts


def audit(research_root: Path, split: str, start: str, end: str,
          candidate_dir: Path, accepted_manifest: Path,
          detector_config: Path, context_config: Path) -> dict:
    root = research_root.resolve()
    folder = candidate_dir.resolve()
    if (split not in ("train", "validation") or split not in SPLITS
            or not SPLITS[split][0] <= start <= end <= SPLITS[split][1]
            or not folder.is_relative_to(root / "data")):
        raise ValueError("audit requires a frozen Train/Validation private prefix")
    verified = source_audit(root, split, start, end, folder,
                            detector_config, context_config)
    accepted_path, manifest = accepted_database(root, accepted_manifest)
    expected = sum(row["candidates"] for row in verified["source_basis_counts"]
                   if row["source"] == DOLT_SOURCE and row["basis"] == "raw")
    counts: Counter[str] = Counter()
    hashes: list[str] = []
    selected = 0
    active_days = 0
    with BoxHistory(root) as provider, duckdb.connect(str(accepted_path), read_only=True) as accepted:
        if provider.semantic_hash != verified["ri_semantic_hash"]:
            raise ValueError("frozen RI semantic hash drift")
        for day_folder in sorted((folder / split).iterdir()):
            if not day_folder.is_dir() or not start <= day_folder.name <= end:
                continue
            files = sorted(day_folder.glob("*.json"))
            hashes.extend(sha256(path.read_bytes()).hexdigest() for path in files)
            requests = candidate_requests(day_folder, split, day_folder.name)
            day_counts = classify_requests(requests, provider.api.core.connection,
                                           accepted, day_folder.name)
            if day_counts:
                active_days += 1
                selected += sum(day_counts.values())
                counts.update(day_counts)
    if (digest(packed(hashes)) != verified["verified_file_set_sha256"]
            or selected != expected):
        raise ValueError("verified candidate file set or source population drift")
    return {"version": VERSION, "split": split, "start": start, "end": end,
            "frozen_sessions": verified["sessions"],
            "source_audit_sha256": _file_sha256(
                Path(__file__).with_name("audit_box_candidate_source_basis.py")),
            "candidate_file_set_sha256": verified["verified_file_set_sha256"],
            "accepted_manifest_sha256": _file_sha256(accepted_manifest),
            "accepted_database_sha256": manifest["database_sha256"],
            "accepted_source_version": manifest["source_version"],
            "ri_semantic_hash": verified["ri_semantic_hash"],
            "audit_source_sha256": _file_sha256(Path(__file__)),
            "dolt_raw_candidate_days": active_days,
            "dolt_raw_candidates": selected,
            "tday_results": dict(sorted(counts.items())),
            "tday_only": True, "future_prices_read": False,
            "future_outcomes_read": False,
            "official_identity_certified": False,
            "corporate_actions_certified": False, "formal_lean_ready": False}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--research-root", type=Path, required=True)
    p.add_argument("--split", choices=("train", "validation"), required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--candidate-dir", type=Path, required=True)
    p.add_argument("--accepted-manifest", type=Path, required=True)
    p.add_argument("--detector-config", type=Path,
                   default=Path("config/box_range_detector_stage_a_v1.yaml"))
    p.add_argument("--context-config", type=Path,
                   default=Path("config/box_lower_band_context_v1.yaml"))
    a = p.parse_args()
    print(json.dumps(audit(a.research_root, a.split, a.start, a.end,
                           a.candidate_dir, a.accepted_manifest,
                           a.detector_config, a.context_config),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

"""Read-only as-of-T issuer-alias observations for sealed daily candidates.

The frozen construction database remains the only evidence source here.
No present-day identity inference, official certification or outcome read.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import duckdb

from radar.box_labeling.history import BoxHistory
from radar.box_labeling.stage_b import digest, packed
from scripts.audit_box_candidate_execution_metadata import candidate_requests
from scripts.audit_box_range_issuer_alias_at_t import (
    classify, construction_source, dated_evidence,
)
from scripts.scan_box_daily_stage_d import SPLITS, source_digest
from scripts.scan_box_near_lower_stage_d import execute

VERSION = "box-candidate-issuer-asof-t-v1"


def build_windows(provider: BoxHistory, requests: list[dict]) -> list[dict]:
    windows = []
    for request in requests:
        history = provider.history(request["security_id"],
                                   request["decision_date"], 126)
        if (history.attrs["source"] != request["source"]
                or history.attrs["basis"] != request["basis"]):
            raise ValueError("candidate/history source or basis drift")
        windows.append({"task_id": request["task_id"],
                        "security_id": request["security_id"],
                        "decision_date": request["decision_date"],
                        "window_start": str(history.date.iloc[0].date())})
    return windows


def audit(research_root: Path, split: str, day: str, candidate_dir: Path,
          private_output: Path, detector_config: Path, context_config: Path) -> dict:
    root, destination = research_root.resolve(), private_output.resolve()
    if not destination.is_relative_to(root / "data"):
        raise ValueError("private output must stay under research-root/data")
    if destination.exists():
        raise FileExistsError("private issuer receipt already exists")
    verified = execute(root, split, day, day, candidate_dir,
                       detector_config, context_config, verify_only=True)
    if not verified["complete"] or verified["sessions"] != 1:
        raise ValueError("candidate day must be complete and verified")
    requests = candidate_requests(candidate_dir.resolve() / split / day, split, day)
    if len(requests) != verified["near_lower_union_rows"]:
        raise ValueError("candidate count drift")
    source_path, construction_hash = construction_source(root)
    with BoxHistory(root) as provider:
        if provider.semantic_hash != verified["ri_semantic_hash"]:
            raise ValueError("RI semantic hash drift")
        windows = build_windows(provider, requests)
    with duckdb.connect(str(source_path), read_only=True) as connection:
        rows = dated_evidence(connection, windows) if windows else []
    if (len(rows) != len(requests)
            or len({row["task_id"] for row in rows}) != len(rows)):
        raise ValueError("issuer audit lost or duplicated candidates")
    for row in rows:
        row["classification"] = classify(row)
    private = {"version": VERSION, "split": split, "decision_date": day,
               "candidate_file_set_sha256": verified["verified_file_set_sha256"],
               "construction_sha256": construction_hash,
               "ri_semantic_hash": verified["ri_semantic_hash"],
               "official_identity_certified": False, "rows": rows}
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = packed(private)
    with destination.open("xb") as stream:
        stream.write(raw)
    return {"version": VERSION, "split": split, "decision_date": day,
            "candidate_file_set_sha256": verified["verified_file_set_sha256"],
            "construction_sha256": construction_hash,
            "ri_semantic_hash": verified["ri_semantic_hash"],
            "audit_source_sha256": source_digest(Path(__file__)),
            "issuer_source_sha256": source_digest(Path(__file__).with_name(
                "audit_box_range_issuer_alias_at_t.py")),
            "private_receipt_sha256": digest(raw), "selected": len(rows),
            "classifications": dict(sorted(Counter(row["classification"]
                                                   for row in rows).items())),
            "other_active_security_id_counts": dict(sorted(Counter(
                row["other_active_security_ids"] for row in rows).items())),
            "official_identity_certified": False,
            "future_outcomes_read": False, "human_labels_read": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--split", choices=tuple(SPLITS), required=True)
    parser.add_argument("--day", required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--private-output", type=Path, required=True)
    parser.add_argument("--detector-config", type=Path,
                        default=Path("config/box_range_detector_stage_a_v1.yaml"))
    parser.add_argument("--context-config", type=Path,
                        default=Path("config/box_lower_band_context_v1.yaml"))
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.split, args.day,
                           args.candidate_dir, args.private_output,
                           args.detector_config, args.context_config),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

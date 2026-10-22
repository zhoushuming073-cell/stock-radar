"""Read-only execution-metadata coverage for sealed near-lower daily candidates.

This reuses the existing split-bounded horizon audit. It never reads future
OHLCV values or turns detector context into an executable order.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from radar.box_labeling.history import BoxHistory
from radar.box_labeling.stage_b import digest, packed
from scripts.audit_box_execution_horizon import HORIZON, horizon_metadata, summarize
from scripts.scan_box_daily_stage_d import SPLITS, source_digest
from scripts.scan_box_near_lower_stage_d import execute

VERSION = "box-candidate-execution-metadata-v1"


def candidate_requests(folder: Path, split: str, day: str) -> list[dict]:
    requests = []
    seen = set()
    for path in sorted(folder.glob("*.json")):
        payload = json.loads(path.read_bytes())["payload"]
        for row in payload["near_contexts"]:
            security_id = row["security_id"]
            if security_id in seen:
                raise ValueError("candidate security identity repeated")
            seen.add(security_id)
            requests.append({"task_id": f"{day}:{security_id}",
                             "security_id": security_id,
                             "decision_date": day, "split": split,
                             "split_end": SPLITS[split][1],
                             "source": row["source"], "basis": row["basis"]})
    return requests


def audit(research_root: Path, split: str, day: str, candidate_dir: Path,
          private_output: Path, detector_config: Path, context_config: Path) -> dict:
    root, destination = research_root.resolve(), private_output.resolve()
    if not destination.is_relative_to(root / "data"):
        raise ValueError("private output must stay under research-root/data")
    if destination.exists():
        raise FileExistsError("private candidate metadata receipt already exists")
    verified = execute(root, split, day, day, candidate_dir,
                       detector_config, context_config, verify_only=True)
    if not verified["complete"] or verified["sessions"] != 1:
        raise ValueError("candidate day must be complete and verified")
    requests = candidate_requests(candidate_dir.resolve() / split / day, split, day)
    if len(requests) != verified["near_lower_union_rows"]:
        raise ValueError("near-lower candidate count drift")
    with BoxHistory(root) as provider:
        if provider.semantic_hash != verified["ri_semantic_hash"]:
            raise ValueError("RI semantic hash drift")
        metadata = (horizon_metadata(provider.api.core.connection, requests)
                    if requests else [])
    private_rows, aggregate = summarize(requests, metadata)
    if aggregate["tasks"] != verified["near_lower_union_rows"]:
        raise ValueError("horizon metadata population drift")
    private = {"version": VERSION, "split": split, "decision_date": day,
               "candidate_file_set_sha256": verified["verified_file_set_sha256"],
               "ri_semantic_hash": verified["ri_semantic_hash"],
               "horizon_sessions": HORIZON, "rows": private_rows,
               "future_prices_read": False, "future_outcomes_read": False,
               "formal_lean_ready": False}
    destination.parent.mkdir(parents=True, exist_ok=True)
    raw = packed(private)
    with destination.open("xb") as stream:
        stream.write(raw)
    return {"version": VERSION, "split": split, "decision_date": day,
            "candidate_file_set_sha256": verified["verified_file_set_sha256"],
            "ri_semantic_hash": verified["ri_semantic_hash"],
            "audit_source_sha256": source_digest(Path(__file__)),
            "horizon_source_sha256": source_digest(Path(__file__).with_name(
                "audit_box_execution_horizon.py")),
            "private_receipt_sha256": digest(raw),
            "horizon_sessions": HORIZON, **aggregate,
            "future_prices_read": False, "future_outcomes_read": False,
            "formal_lean_ready": False}


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

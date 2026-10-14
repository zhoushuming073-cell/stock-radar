"""Aggregate intersection of sealed issuer and raw-metadata candidate audits."""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

from radar.box_labeling.stage_b import digest


def _read(path: Path, expected_sha256: str) -> dict:
    raw = path.read_bytes()
    if digest(raw) != expected_sha256:
        raise ValueError("private gate receipt hash mismatch")
    return json.loads(raw)


def raw_complete(task: dict, horizon: int) -> bool:
    return (task["complete_horizon_within_split"] is True
            and len(task["sessions"]) == horizon
            and all(row["same_source_raw_rows"] == 1
                    and row["raw_ready"] is True
                    and not row["raw_identity_flag"]
                    and not row["raw_split_flag"]
                    for row in task["sessions"]))


def summarize(issuer_path: Path, issuer_sha256: str,
              metadata_path: Path, metadata_sha256: str) -> dict:
    issuer = _read(issuer_path, issuer_sha256)
    metadata = _read(metadata_path, metadata_sha256)
    if (issuer["split"] != metadata["split"]
            or issuer["decision_date"] != metadata["decision_date"]
            or issuer["candidate_file_set_sha256"] != metadata["candidate_file_set_sha256"]
            or issuer["ri_semantic_hash"] != metadata["ri_semantic_hash"]
            or issuer["official_identity_certified"] is not False
            or metadata["formal_lean_ready"] is not False):
        raise ValueError("issuer and metadata populations or gates differ")
    issuers = {row["task_id"]: row for row in issuer["rows"]}
    tasks = {row["task_id"]: row for row in metadata["rows"]}
    if (len(issuers) != len(issuer["rows"])
            or len(tasks) != len(metadata["rows"])
            or set(issuers) != set(tasks)):
        raise ValueError("candidate task identity sets do not match")
    counts = Counter((issuer_row["classification"],
                      raw_complete(tasks[task_id], metadata["horizon_sessions"]))
                     for task_id, issuer_row in issuers.items())
    return {"split": issuer["split"], "decision_date": issuer["decision_date"],
            "candidate_file_set_sha256": issuer["candidate_file_set_sha256"],
            "issuer_receipt_sha256": issuer_sha256,
            "metadata_receipt_sha256": metadata_sha256,
            "candidates": len(issuers),
            "classification_by_raw_metadata_complete": {
                f"{classification}|raw_complete={str(ready).lower()}": count
                for (classification, ready), count in sorted(counts.items())},
            "official_identity_certified": False,
            "formal_lean_ready": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--issuer", type=Path, required=True)
    parser.add_argument("--issuer-sha256", required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--metadata-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(summarize(args.issuer, args.issuer_sha256,
                               args.metadata, args.metadata_sha256),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

"""Read-only, source-stratified intersection of sealed candidate gate receipts.

This binds candidate source/basis rows to existing as-of-T issuer and
metadata-only horizon audits. It cannot certify identity or execution prices.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from radar.box_labeling.stage_b import digest, packed
from scripts.audit_box_candidate_execution_metadata import candidate_requests
from scripts.summarize_box_candidate_gates import raw_complete, summarize

VERSION = "box-candidate-source-gates-v1"


def source_strata(candidate_root: Path, issuer_path: Path, issuer_sha256: str,
                  metadata_path: Path, metadata_sha256: str) -> dict:
    gate = summarize(issuer_path, issuer_sha256, metadata_path, metadata_sha256)
    issuer = json.loads(issuer_path.read_bytes())
    metadata = json.loads(metadata_path.read_bytes())
    folder = candidate_root / gate["split"] / gate["decision_date"]
    files = sorted(folder.glob("*.json"))
    if not files or any(folder.glob("*.partial")):
        raise ValueError("candidate chunks missing or partial")
    file_set_sha256 = digest(packed([sha256(path.read_bytes()).hexdigest()
                                     for path in files]))
    if file_set_sha256 != gate["candidate_file_set_sha256"]:
        raise ValueError("candidate file set differs from gate receipts")
    requests = candidate_requests(folder, gate["split"], gate["decision_date"])
    sources = {}
    for request in requests:
        if (not request["source"] or request["basis"] not in ("raw", "split")):
            raise ValueError("candidate source or basis invalid")
        sources[request["task_id"]] = (request["source"], request["basis"])
    issuers = {row["task_id"]: row for row in issuer["rows"]}
    tasks = {row["task_id"]: row for row in metadata["rows"]}
    if len(requests) != gate["candidates"] or set(sources) != set(issuers):
        raise ValueError("candidate source and gate task sets differ")
    counts = Counter((source, basis, issuers[task_id]["classification"],
                      raw_complete(tasks[task_id], metadata["horizon_sessions"]))
                     for task_id, (source, basis) in sources.items())
    return {"version": VERSION, "split": gate["split"],
            "decision_date": gate["decision_date"],
            "candidate_file_set_sha256": file_set_sha256,
            "issuer_receipt_sha256": issuer_sha256,
            "metadata_receipt_sha256": metadata_sha256,
            "audit_source_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
            "candidates": gate["candidates"],
            "source_basis_gate_counts": [
                {"source": source, "basis": basis,
                 "issuer_classification": classification,
                 "raw_metadata_complete": ready, "candidates": count}
                for (source, basis, classification, ready), count in sorted(counts.items())],
            "official_identity_certified": False,
            "future_prices_read": False, "future_outcomes_read": False,
            "formal_lean_ready": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--issuer", type=Path, required=True)
    parser.add_argument("--issuer-sha256", required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--metadata-sha256", required=True)
    args = parser.parse_args()
    print(json.dumps(source_strata(args.candidate_root, args.issuer,
                                    args.issuer_sha256, args.metadata,
                                    args.metadata_sha256), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

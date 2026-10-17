"""Read-only T-day overlap between sealed Dolt candidates and accepted raw bars.

This audits one historical close already visible when the candidate was made.
It never reads T+1 prices or promotes research-grade bars to LEAN inputs.
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
from scripts.summarize_box_candidate_gates import raw_complete
from scripts.summarize_box_candidate_source_gates import source_strata

VERSION = "box-candidate-tday-price-bridge-v1"
DOLT_SOURCE = "Dolt:post-no-preference/stocks"
ACCEPTED_PROVENANCE = ("Dolt", "post-no-preference/stocks", "raw")


def _file_sha256(path: Path) -> str:
    hasher = sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def accepted_database(root: Path, manifest_path: Path) -> tuple[Path, dict]:
    manifest = json.loads(manifest_path.read_bytes())
    path = Path(manifest["database"]).resolve()
    if (not path.is_relative_to(root.resolve() / "data")
            or manifest["quality_tier"] != "research-grade"
            or manifest["price_basis"] != "raw"
            or manifest["source_version"] == ""
            or manifest["license"] == ""
            or _file_sha256(path) != manifest["database_sha256"]):
        raise ValueError("accepted raw price manifest or database drift")
    return path, manifest


def compare_tday(shape_connection, accepted_connection,
                 security_id: str, decision_date: str) -> str:
    shape = shape_connection.execute("""SELECT symbol,open,high,low,close,volume
        FROM shape_price WHERE security_id=? AND date=?
          AND source='Dolt:post-no-preference/stocks' AND basis='raw'""",
        [security_id, decision_date]).fetchall()
    accepted = accepted_connection.execute("""SELECT symbol,open,high,low,close,volume,
          provider,feed,adjustment FROM daily_bars
        WHERE security_id=? AND date=?""", [security_id, decision_date]).fetchall()
    if len(shape) != 1:
        return "shape_tday_missing" if not shape else "shape_tday_nonunique"
    if len(accepted) != 1:
        return "accepted_tday_missing" if not accepted else "accepted_tday_nonunique"
    if accepted[0][6:] != ACCEPTED_PROVENANCE:
        return "accepted_provenance_mismatch"
    if shape[0][0] != accepted[0][0]:
        return "symbol_mismatch"
    if shape[0][1:] != accepted[0][1:6]:
        return "tday_ohlcv_mismatch"
    return "exact_tday_match"


def audit(research_root: Path, gate_evidence_path: Path,
          accepted_manifest_path: Path) -> dict:
    root = research_root.resolve()
    private = root / "data/box-range-stage-d"
    evidence = json.loads(gate_evidence_path.read_bytes())
    if evidence["version"] != "box-candidate-source-gates-acceptance-v1":
        raise ValueError("unexpected source-gate evidence version")
    accepted_path, accepted_manifest = accepted_database(root, accepted_manifest_path)
    selected: list[tuple[str, str, str]] = []
    days = set()
    semantic_hashes = set()
    for item in evidence["days"]:
        split, day = item["split"], item["decision_date"]
        if split not in ("train", "validation") or (split, day) in days:
            raise ValueError("duplicate or forbidden source-gate day")
        days.add((split, day))
        name = f"{split}-{day}.json"
        folder = private / "near-lower-candidate-v1" / split / day
        strata = source_strata(private / "near-lower-candidate-v1",
            private / "issuer-candidates-v1" / name, item["issuer_receipt_sha256"],
            private / "execution-metadata-candidates-v1" / name,
            item["metadata_receipt_sha256"])
        if strata["candidate_file_set_sha256"] != item["candidate_file_set_sha256"]:
            raise ValueError("source-gate candidate file-set drift")
        issuer_raw = (private / "issuer-candidates-v1" / name).read_bytes()
        metadata_raw = (private / "execution-metadata-candidates-v1" / name).read_bytes()
        if (digest(issuer_raw) != item["issuer_receipt_sha256"]
                or digest(metadata_raw) != item["metadata_receipt_sha256"]):
            raise ValueError("source-gate receipt changed during audit")
        issuer, metadata = json.loads(issuer_raw), json.loads(metadata_raw)
        semantic_hashes.add(issuer["ri_semantic_hash"])
        classes = {row["task_id"]: row["classification"] for row in issuer["rows"]}
        horizons = {row["task_id"]: row for row in metadata["rows"]}
        files = sorted(folder.glob("*.json"))
        if digest(packed([_file_sha256(path) for path in files])) != strata["candidate_file_set_sha256"]:
            raise ValueError("candidate files changed during audit")
        for request in candidate_requests(folder, split, day):
            task = request["task_id"]
            if (request["source"] == DOLT_SOURCE and request["basis"] == "raw"
                    and classes[task] == "OBSERVATIONAL_NO_KNOWN_CONFLICT"
                    and raw_complete(horizons[task], metadata["horizon_sessions"])):
                selected.append((request["security_id"], day, split))
    expected = sum(item["dolt_raw"]["observational_and_raw_complete"]
                   for item in evidence["days"])
    if len(selected) != expected or len(set(selected)) != len(selected):
        raise ValueError("selected source-gate population drift")
    counts = Counter()
    by_day: dict[tuple[str, str], Counter] = {key: Counter() for key in days}
    with BoxHistory(root) as history, duckdb.connect(str(accepted_path), read_only=True) as accepted:
        if semantic_hashes != {history.semantic_hash}:
            raise ValueError("frozen RI semantic hash drift")
        for security_id, day, split in selected:
            result = compare_tday(history.api.core.connection, accepted, security_id, day)
            counts[result] += 1
            by_day[(split, day)][result] += 1
    return {"version": VERSION, "gate_evidence_sha256": _file_sha256(gate_evidence_path),
            "accepted_manifest_sha256": _file_sha256(accepted_manifest_path),
            "accepted_database_sha256": accepted_manifest["database_sha256"],
            "accepted_source_version": accepted_manifest["source_version"],
            "accepted_license": accepted_manifest["license"],
            "accepted_manifest_status": accepted_manifest["status"],
            "audit_source_sha256": _file_sha256(Path(__file__)),
            "ri_semantic_hash": next(iter(semantic_hashes)),
            "selected": len(selected), "tday_results": dict(sorted(counts.items())),
            "by_day": [{"split": split, "decision_date": day,
                        "selected": sum(by_day[(split, day)].values()),
                        "tday_results": dict(sorted(by_day[(split, day)].items()))}
                       for split, day in sorted(days)],
            "tday_only": True, "future_prices_read": False,
            "future_outcomes_read": False, "official_identity_certified": False,
            "corporate_actions_certified": False, "formal_lean_ready": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--gate-evidence", type=Path, required=True)
    parser.add_argument("--accepted-manifest", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.gate_evidence,
                           args.accepted_manifest), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

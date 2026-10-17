"""Metadata-only accepted-raw horizon audit after exact candidate T-day match.

The ten sessions are a data-coverage probe, not an exit rule. Only session
dates, symbol, provider, feed and adjustment are read after decision close T.
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
from scripts.audit_box_candidate_tday_price_bridge import (
    ACCEPTED_PROVENANCE, DOLT_SOURCE, _file_sha256, accepted_database,
    audit as audit_tday, compare_tday,
)
from scripts.scan_box_daily_stage_d import SPLITS
from scripts.summarize_box_candidate_gates import raw_complete

VERSION = "box-candidate-accepted-horizon-v1"
HORIZON = 10  # Coverage diagnostic only; not a holding-period rule.


def accepted_session_metadata(connection, security_id: str, sessions: list[str],
                              tday_symbol: str) -> dict:
    counts: Counter[str] = Counter()
    for day in sessions:
        rows = connection.execute("""SELECT symbol,provider,feed,adjustment
            FROM daily_bars WHERE security_id=? AND date=?""",
            [security_id, day]).fetchall()
        if not rows:
            counts["missing"] += 1
        elif len(rows) != 1:
            counts["nonunique"] += 1
        elif rows[0][1:] != ACCEPTED_PROVENANCE:
            counts["provenance_mismatch"] += 1
        else:
            counts["matching_raw"] += 1
            if rows[0][0] != tday_symbol:
                counts["symbol_transition"] += 1
    return dict(counts)


def audit(research_root: Path, gate_evidence_path: Path,
          accepted_manifest_path: Path) -> dict:
    root = research_root.resolve()
    private = root / "data/box-range-stage-d"
    tday = audit_tday(root, gate_evidence_path, accepted_manifest_path)
    if not tday["tday_only"] or tday["future_prices_read"] is not False:
        raise ValueError("T-day bridge contract drift")
    evidence = json.loads(gate_evidence_path.read_bytes())
    accepted_path, _ = accepted_database(root, accepted_manifest_path)
    totals: Counter[str] = Counter()
    per_day: dict[tuple[str, str], Counter[str]] = {}
    selected = 0
    with BoxHistory(root) as provider, duckdb.connect(str(accepted_path), read_only=True) as accepted:
        if provider.semantic_hash != tday["ri_semantic_hash"]:
            raise ValueError("frozen RI semantic hash drift")
        for item in evidence["days"]:
            split, day = item["split"], item["decision_date"]
            if split not in ("train", "validation") or provider.api.profile[
                    "semantics"]["frozen_splits"].get(split) != list(SPLITS[split]):
                raise ValueError("frozen split contract drift")
            name = f"{split}-{day}.json"
            folder = private / "near-lower-candidate-v1" / split / day
            files = sorted(folder.glob("*.json"))
            if (digest(packed([_file_sha256(path) for path in files]))
                    != item["candidate_file_set_sha256"]):
                raise ValueError("candidate receipt changed after T-day audit")
            issuer_raw = (private / "issuer-candidates-v1" / name).read_bytes()
            metadata_raw = (private / "execution-metadata-candidates-v1" / name).read_bytes()
            if (digest(issuer_raw) != item["issuer_receipt_sha256"]
                    or digest(metadata_raw) != item["metadata_receipt_sha256"]):
                raise ValueError("private gate receipt changed after T-day audit")
            issuer, metadata = json.loads(issuer_raw), json.loads(metadata_raw)
            classes = {row["task_id"]: row["classification"] for row in issuer["rows"]}
            horizons = {row["task_id"]: row for row in metadata["rows"]}
            day_counts: Counter[str] = Counter()
            for request in candidate_requests(folder, split, day):
                task = request["task_id"]
                if not (request["source"] == DOLT_SOURCE and request["basis"] == "raw"
                        and classes[task] == "OBSERVATIONAL_NO_KNOWN_CONFLICT"
                        and raw_complete(horizons[task], metadata["horizon_sessions"])):
                    continue
                sid = request["security_id"]
                if compare_tday(provider.api.core.connection, accepted, sid, day) != "exact_tday_match":
                    continue
                selected += 1
                day_counts["tday_exact"] += 1
                tday_symbol = accepted.execute("""SELECT symbol FROM daily_bars
                    WHERE security_id=? AND date=?""", [sid, day]).fetchone()[0]
                sessions = [str(row[0]) for row in provider.api.core.connection.execute(
                    "SELECT date FROM sessions WHERE date>? AND date<=? ORDER BY date LIMIT ?",
                    [day, request["split_end"], HORIZON]).fetchall()]
                day_counts["expected_sessions"] += len(sessions)
                session_counts = accepted_session_metadata(accepted, sid, sessions, tday_symbol)
                day_counts.update(session_counts)
                if len(sessions) != HORIZON:
                    day_counts["split_censored_tasks"] += 1
                elif session_counts.get("matching_raw", 0) == HORIZON:
                    day_counts["complete_metadata_tasks"] += 1
            per_day[(split, day)] = day_counts
            totals.update(day_counts)
    if selected != tday["tday_results"].get("exact_tday_match", 0):
        raise ValueError("T-day exact-match population drift")
    return {"version": VERSION,
            "gate_evidence_sha256": _file_sha256(gate_evidence_path),
            "tday_auditor_sha256": tday["audit_source_sha256"],
            "accepted_database_sha256": tday["accepted_database_sha256"],
            "audit_source_sha256": _file_sha256(Path(__file__)),
            "ri_semantic_hash": tday["ri_semantic_hash"],
            "horizon_sessions_diagnostic_only": HORIZON,
            "selected_tday_exact": selected,
            "totals": dict(sorted(totals.items())),
            "by_day": [{"split": split, "decision_date": day,
                        **dict(sorted(counts.items()))}
                       for (split, day), counts in sorted(per_day.items())],
            "future_price_values_read": False, "future_outcomes_read": False,
            "official_identity_certified": False,
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

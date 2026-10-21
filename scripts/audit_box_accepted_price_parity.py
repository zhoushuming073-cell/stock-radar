"""Compare same-source raw OHLCV for the bounded private CTA follow-up queue.

This is a price-data equality check, not a signal, outcome, holding rule or
portfolio simulation. It reads post-T prices solely to compare two stored
copies of the same source and keeps every identifier and price out of stdout.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import duckdb

from radar.box_labeling.history import BoxHistory
from scripts.audit_box_candidate_tday_price_bridge import (
    ACCEPTED_PROVENANCE, DOLT_SOURCE, accepted_database,
)
from scripts.audit_box_cta_full_coverage import START, END
from scripts.audit_box_cta_raw_gate_intersection import VERSION as QUEUE_VERSION

VERSION = "box-accepted-raw-price-parity-v1"
HORIZON = 10  # Coverage/parity diagnostic, not an exit rule.
PRICE_FIELDS = ("symbol", "open", "high", "low", "close", "volume")


def classify(shape_rows: list[tuple], accepted_rows: list[tuple]) -> str:
    if len(shape_rows) != 1:
        return "shape_missing" if not shape_rows else "shape_nonunique"
    if len(accepted_rows) != 1:
        return "accepted_missing" if not accepted_rows else "accepted_nonunique"
    if accepted_rows[0][len(PRICE_FIELDS):] != ACCEPTED_PROVENANCE:
        return "accepted_provenance_mismatch"
    if shape_rows[0][0] != accepted_rows[0][0]:
        return "symbol_mismatch"
    if shape_rows[0][1:] != accepted_rows[0][1:len(PRICE_FIELDS)]:
        return "ohlcv_mismatch"
    return "exact"


def audit(root: Path, queue_path: Path, accepted_manifest: Path,
          full_receipt_path: Path) -> dict:
    root, queue_path = root.resolve(), queue_path.resolve()
    if not queue_path.is_relative_to(root / "data"):
        raise ValueError("private queue must remain under research-root/data")
    queue_raw = queue_path.read_bytes()
    queue = json.loads(queue_raw)
    full = json.loads(full_receipt_path.read_bytes())
    if (queue.get("version") != QUEUE_VERSION
            or queue.get("formal_lean_ready") is not False
            or full.get("version") != "box-cta-full-covered-validation-v1"
            or queue.get("candidate_file_set_sha256")
            != full.get("candidate_file_set_sha256")):
        raise ValueError("private queue/full candidate receipt mismatch")
    rows = queue["rows"]
    if (not rows or len({(r["security_id"], r["decision_date"]) for r in rows})
            != len(rows) or any(not START <= r["decision_date"] <= END
                                   for r in rows)):
        raise ValueError("invalid or duplicated queue population")
    accepted_path, accepted = accepted_database(root, accepted_manifest)
    totals: Counter[str] = Counter()
    task_status: Counter[str] = Counter()
    pairs: set[tuple[str, str]] = set()
    with BoxHistory(root) as provider, duckdb.connect(str(accepted_path), read_only=True) as prices:
        if provider.semantic_hash != full["ri_semantic_hash"]:
            raise ValueError("frozen Research Infrastructure semantics drift")
        shape = provider.api.core.connection
        for row in rows:
            sid, day = row["security_id"], row["decision_date"]
            sessions = [str(item[0]) for item in shape.execute(
                "SELECT date FROM sessions WHERE date>? AND date<=? "
                "ORDER BY date LIMIT ?", [day, END, HORIZON]).fetchall()]
            if len(sessions) != HORIZON:
                raise ValueError("queued task lacks ten in-split sessions")
            shape_rows = shape.execute(
                "SELECT date,symbol,open,high,low,close,volume FROM shape_price "
                "WHERE security_id=? AND source=? AND basis='raw' "
                "AND date IN (SELECT CAST(unnest(?) AS DATE))",
                [sid, DOLT_SOURCE, sessions],
            ).fetchall()
            accepted_rows = prices.execute(
                "SELECT date,symbol,open,high,low,close,volume,provider,feed,adjustment "
                "FROM daily_bars WHERE security_id=? "
                "AND date IN (SELECT CAST(unnest(?) AS DATE))",
                [sid, sessions],
            ).fetchall()
            shape_by_day: dict[str, list[tuple]] = {}
            accepted_by_day: dict[str, list[tuple]] = {}
            for item in shape_rows:
                shape_by_day.setdefault(str(item[0]), []).append(item[1:])
            for item in accepted_rows:
                accepted_by_day.setdefault(str(item[0]), []).append(item[1:])
            statuses = []
            for session in sessions:
                status = classify(shape_by_day.get(session, []),
                                  accepted_by_day.get(session, []))
                totals[status] += 1
                statuses.append(status)
                pairs.add((sid, session))
            task_status["all_exact" if all(s == "exact" for s in statuses)
                        else "not_all_exact"] += 1
    return {
        "version": VERSION, "split": "validation", "start": START, "end": END,
        "private_queue_sha256": sha256(queue_raw).hexdigest(),
        "full_cta_receipt_sha256": sha256(full_receipt_path.read_bytes()).hexdigest(),
        "candidate_file_set_sha256": full["candidate_file_set_sha256"],
        "ri_semantic_hash": full["ri_semantic_hash"],
        "accepted_database_sha256": accepted["database_sha256"],
        "candidate_days": len(rows),
        "observed_security_ids": len({r["security_id"] for r in rows}),
        "diagnostic_horizon_sessions": HORIZON,
        "candidate_session_comparisons": sum(totals.values()),
        "distinct_security_session_pairs": len(pairs),
        "session_status": dict(sorted(totals.items())),
        "candidate_status": dict(sorted(task_status.items())),
        "future_price_values_read_for_source_parity_only": True,
        "future_outcomes_read": False,
        "official_identity_certified": False,
        "corporate_actions_certified": False,
        "portfolio_rules_frozen": False,
        "formal_lean_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--private-queue", type=Path, required=True)
    parser.add_argument("--accepted-manifest", type=Path, required=True)
    parser.add_argument("--full-cta-receipt", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.private_queue,
                           args.accepted_manifest, args.full_cta_receipt),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

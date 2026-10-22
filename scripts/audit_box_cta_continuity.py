"""Audit post-close CTA symbol continuity for a private bounded box cohort.

This diagnostic reads T and following-session symbols, not prices or returns.
It neither certifies official historical class/issuer identity nor promotes
any candidate to formal LEAN execution.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from radar.box_labeling.history import BoxHistory
from scripts.audit_box_accepted_price_parity import HORIZON
from scripts.audit_box_candidate_tday_price_bridge import DOLT_SOURCE
from scripts.audit_box_cta_full_coverage import START, END
from scripts.audit_box_cta_raw_gate_intersection import VERSION as QUEUE_VERSION
from scripts.audit_box_cta_symbol_coverage import parse_cta

VERSION = "box-cta-continuity-v1"
FIELDS = ("PrimaryListingMarketParticipantID", "InstrumentType", "HaltReason",
          "Test", "IPO", "FinancialStatusIndicator")


def classify(t_symbol: str, current_symbol: str,
             t: dict[str, str] | None, current: dict[str, str] | None) -> set[str]:
    """Return nonexclusive diagnostic flags; absence and class drift fail open nowhere."""
    flags: set[str] = set()
    if current_symbol != t_symbol:
        flags.add("source_symbol_changed")
    if t is None:
        flags.add("t_cta_symbol_absent")
    if current is None:
        flags.add("cta_symbol_absent")
        return flags
    if current["PrimaryListingMarketParticipantID"].strip() != "N":
        flags.add("listing_market_not_nyse")
    if current["InstrumentType"].strip() != "0":
        flags.add("instrument_not_cta_equity")
    if t is not None:
        for field, name in (("PrimaryListingMarketParticipantID", "listing_market_changed"),
                            ("InstrumentType", "instrument_type_changed")):
            if current[field].strip() != t[field].strip():
                flags.add(name)
    if current["HaltReason"].strip():
        flags.add("halt_reason_present")
    if current["Test"].strip() != "0":
        flags.add("test_flag_nonzero")
    if current["IPO"].strip() != "0":
        flags.add("ipo_flag_nonzero")
    if current["FinancialStatusIndicator"].strip() != "0":
        flags.add("financial_status_nonzero")
    return flags


def audit(root: Path, queue_path: Path, parity_path: Path,
          cta_receipt_path: Path, sec_receipt_path: Path, cta_dir: Path) -> dict:
    root, queue_path, cta_dir = (p.resolve() for p in (root, queue_path, cta_dir))
    if (not queue_path.is_relative_to(root / "data")
            or not cta_dir.is_relative_to(root / "data")):
        raise ValueError("queue and CTA sources must stay in private data")
    queue_raw, parity_raw, full_raw, sec_raw = (p.read_bytes() for p in
                                              (queue_path, parity_path,
                                               cta_receipt_path, sec_receipt_path))
    queue, parity, full, sec = (json.loads(raw) for raw in
                                (queue_raw, parity_raw, full_raw, sec_raw))
    rows = queue.get("rows")
    if (queue.get("version") != QUEUE_VERSION
            or queue.get("formal_lean_ready") is not False
            or not isinstance(rows, list) or not rows
            or len({(r["security_id"], r["decision_date"]) for r in rows}) != len(rows)
            or parity.get("private_queue_sha256") != sha256(queue_raw).hexdigest()
            or parity.get("candidate_status") != {"all_exact": len(rows)}
            or parity.get("formal_lean_ready") is not False
            or full.get("version") != "box-cta-full-covered-validation-v1"
            or full.get("candidate_file_set_sha256")
            != queue.get("candidate_file_set_sha256")
            or full.get("sessions") != len(full.get("cta_snapshot_hashes", []))
            or full.get("start") != START or full.get("end") != END
            or sec.get("version") != "box-sec-class-observation-coverage-v1"
            or sec.get("private_queue_sha256") != sha256(queue_raw).hexdigest()
            or sec.get("reviewed_candidate_days") != len(rows)
            or sec.get("reviewed_observed_security_ids")
            != len({r["security_id"] for r in rows})
            or sec.get("formal_lean_ready") is not False):
        raise ValueError("frozen cohort/source receipt mismatch")
    snapshots: dict[str, dict] = {}
    snapshot_hashes = full["cta_snapshot_hashes"]
    for item in snapshot_hashes:
        day = item["date"]
        if day in snapshots or not START <= day <= END:
            raise ValueError("duplicate or out-of-scope CTA day")
        path = cta_dir / f"CTA.Symbol.File.{day.replace('-', '')}.csv"
        if sha256(path.read_bytes()).hexdigest() != item["sha256"]:
            raise ValueError("CTA snapshot bytes changed")
        snapshots[day] = parse_cta(path, day)
    counters: Counter[str] = Counter()
    affected: Counter[str] = Counter()
    t_market: Counter[str] = Counter()
    t_instrument: Counter[str] = Counter()
    t_missing = 0
    pairs: set[tuple[str, str]] = set()
    with BoxHistory(root) as provider:
        if provider.semantic_hash != parity["ri_semantic_hash"]:
            raise ValueError("frozen RI semantics changed")
        connection = provider.api.core.connection
        for row in rows:
            sid, day, symbol = (row[key] for key in
                                ("security_id", "decision_date", "symbol"))
            if day not in snapshots:
                raise ValueError("candidate T lacks CTA snapshot")
            horizon = [str(r[0]) for r in connection.execute(
                "SELECT date FROM sessions WHERE date>? AND date<=? "
                "ORDER BY date LIMIT ?", [day, END, HORIZON]).fetchall()]
            if len(horizon) != HORIZON or any(d not in snapshots for d in horizon):
                raise ValueError("candidate horizon lacks ten CTA sessions")
            days = [day, *horizon]
            source_rows = connection.execute(
                "SELECT date,symbol FROM shape_price WHERE security_id=? "
                "AND source=? AND basis='raw' "
                "AND date IN (SELECT CAST(unnest(?) AS DATE))",
                [sid, DOLT_SOURCE, days]).fetchall()
            by_day: dict[str, list[str]] = {}
            for source_day, source_symbol in source_rows:
                by_day.setdefault(str(source_day), []).append(source_symbol)
            if any(len(by_day.get(source_day, [])) != 1 for source_day in days):
                raise ValueError("missing or duplicated raw symbol in cohort horizon")
            if by_day[day][0] != symbol:
                raise ValueError("queue T symbol changed")
            t = snapshots[day].get(symbol)
            if t is None:
                t_missing += 1
            else:
                t_market[t["PrimaryListingMarketParticipantID"].strip()] += 1
                t_instrument[t["InstrumentType"].strip()] += 1
            row_flags: set[str] = set()
            for source_day in days:
                current_symbol = by_day[source_day][0]
                current = snapshots[source_day].get(current_symbol)
                flags = classify(symbol, current_symbol, t, current)
                counters.update(flags)
                row_flags.update(flags)
                pairs.add((sid, source_day))
            affected.update(row_flags)
    return {
        "version": VERSION, "split": "validation", "start": START, "end": END,
        "private_queue_sha256": sha256(queue_raw).hexdigest(),
        "price_parity_receipt_sha256": sha256(parity_raw).hexdigest(),
        "full_cta_receipt_sha256": sha256(full_raw).hexdigest(),
        "sec_class_receipt_sha256": sha256(sec_raw).hexdigest(),
        "cta_snapshot_days": len(snapshots),
        "candidate_days": len(rows), "observed_security_ids": len({r["security_id"] for r in rows}),
        "diagnostic_horizon_sessions_after_t": HORIZON,
        "candidate_snapshot_checks": len(rows) * (HORIZON + 1),
        "distinct_security_snapshot_pairs": len(pairs),
        "t_cta_absent_candidate_days": t_missing,
        "t_listing_market_codes": dict(sorted(t_market.items())),
        "t_instrument_type_codes": dict(sorted(t_instrument.items())),
        "flagged_snapshot_checks": dict(sorted(counters.items())),
        "candidate_days_with_flags": dict(sorted(affected.items())),
        "cta_post_close_only": True,
        "historical_identity_certified": False,
        "corporate_actions_certified": False,
        "future_outcomes_read": False, "formal_lean_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--private-queue", type=Path, required=True)
    parser.add_argument("--price-parity-receipt", type=Path, required=True)
    parser.add_argument("--full-cta-receipt", type=Path, required=True)
    parser.add_argument("--sec-class-receipt", type=Path, required=True)
    parser.add_argument("--cta-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.private_queue,
                           args.price_parity_receipt,
                           args.full_cta_receipt, args.sec_class_receipt,
                           args.cta_dir),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

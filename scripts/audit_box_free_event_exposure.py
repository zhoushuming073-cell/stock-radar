"""Locate pinned-source split/dividend review leads for a private box cohort.

Post-T event dates are read only for diagnostic coverage. No trade, entitlement,
outcome or return is inferred. Stdout contains aggregate counts only.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from hashlib import sha256
import json
from pathlib import Path

from radar.box_labeling.history import BoxHistory
from scripts.audit_box_accepted_price_parity import HORIZON
from scripts.audit_box_cta_full_coverage import END, START
from scripts.audit_box_cta_raw_gate_intersection import VERSION as QUEUE_VERSION

VERSION = "box-free-event-exposure-v1"


def parse_scan(raw: bytes, kind: str, expected_version: str,
               earliest: str, latest: str) -> tuple[dict, dict[tuple[str, str], list[dict]]]:
    data = json.loads(raw)
    coverage = data.get("coverage")
    if (not isinstance(coverage, list) or len(coverage) != 2
            or not all(isinstance(day, str) for day in coverage)):
        raise ValueError("invalid event scan coverage")
    if (data.get("table") != kind or data.get("error")
            or data.get("source_version") != expected_version
            or coverage[0] > earliest or coverage[1] < latest
            or data.get("receipt", {}).get("status") != 200
            or data.get("receipt", {}).get("error") is not None
            or not isinstance(data.get("events"), list)):
        raise ValueError("incomplete or mismatched pinned event scan")
    by_key: dict[tuple[str, str], list[dict]] = {}
    for row in data["events"]:
        symbol = row.get("symbol")
        when = str(row.get("date", ""))[:10]
        if (not isinstance(symbol, str) or not symbol or not when
                or date.fromisoformat(when).isoformat() != when):
            raise ValueError("invalid event row")
        by_key.setdefault((symbol, when), []).append(row)
    return data, by_key


def audit(root: Path, queue_path: Path, parity_path: Path,
          rules_path: Path, split_path: Path, dividend_path: Path) -> dict:
    root, queue_path = root.resolve(), queue_path.resolve()
    if not queue_path.is_relative_to(root / "data"):
        raise ValueError("private queue must be under research-root/data")
    queue_raw = queue_path.read_bytes()
    queue = json.loads(queue_raw)
    parity = json.loads(parity_path.read_bytes())
    rows = queue.get("rows")
    if (queue.get("version") != QUEUE_VERSION
            or queue.get("formal_lean_ready") is not False
            or not isinstance(rows, list) or not rows
            or len({(r["security_id"], r["decision_date"]) for r in rows}) != len(rows)
            or parity.get("private_queue_sha256") != sha256(queue_raw).hexdigest()
            or parity.get("candidate_days") != len(rows)
            or parity.get("candidate_status") != {"all_exact": len(rows)}
            or parity.get("formal_lean_ready") is not False):
        raise ValueError("private queue/price-parity receipt mismatch")
    rules_raw = rules_path.read_bytes()
    rules = json.loads(rules_raw)
    pin = rules["prices"]["source_version"]
    scans = {}
    for kind, path in (("split", split_path), ("dividend", dividend_path)):
        raw = path.read_bytes()
        data, index = parse_scan(raw, kind, pin, START, END)
        scans[kind] = (raw, data, index)
    counts: Counter[str] = Counter()
    unique: dict[str, set[tuple[str, str]]] = {kind: set() for kind in scans}
    with BoxHistory(root) as provider:
        if provider.semantic_hash != parity["ri_semantic_hash"]:
            raise ValueError("frozen Research Infrastructure semantics drift")
        c = provider.api.core.connection
        for row in rows:
            day, symbol = row["decision_date"], row["symbol"]
            if not START <= day <= END:
                raise ValueError("candidate outside covered Validation interval")
            sessions = [str(r[0]) for r in c.execute(
                "SELECT date FROM sessions WHERE date>? AND date<=? "
                "ORDER BY date LIMIT ?", [day, END, HORIZON]).fetchall()]
            if len(sessions) != HORIZON:
                raise ValueError("incomplete in-split diagnostic horizon")
            for kind, (_, _, index) in scans.items():
                hits = [(session, event) for session in sessions
                        for event in index.get((symbol, session), [])]
                if hits:
                    counts[f"{kind}_candidate_days"] += 1
                    counts[f"{kind}_candidate_event_rows"] += len(hits)
                    unique[kind].update((symbol, session) for session, _ in hits)
    return {
        "version": VERSION, "split": "validation", "start": START, "end": END,
        "private_queue_sha256": sha256(queue_raw).hexdigest(),
        "price_parity_receipt_sha256": sha256(parity_path.read_bytes()).hexdigest(),
        "rules_sha256": sha256(rules_raw).hexdigest(), "event_source_version": pin,
        "scan_sha256": {kind: sha256(raw).hexdigest()
                        for kind, (raw, _, _) in sorted(scans.items())},
        "scan_event_rows": {kind: len(data["events"])
                            for kind, (_, data, _) in sorted(scans.items())},
        "candidate_days": len(rows), "diagnostic_horizon_sessions": HORIZON,
        "exposure": {kind: {
            "candidate_days": counts[f"{kind}_candidate_days"],
            "candidate_event_rows": counts[f"{kind}_candidate_event_rows"],
            "distinct_symbol_dates": len(unique[kind]),
        } for kind in sorted(scans)},
        "event_scan_complete_coverage_certified": False,
        "cash_entitlement_certified": False,
        "official_identity_certified": False,
        "future_outcomes_read": False, "formal_lean_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--private-queue", type=Path, required=True)
    parser.add_argument("--price-parity-receipt", type=Path, required=True)
    parser.add_argument("--rules", type=Path,
                        default=Path("config/pit_research_grade_rules.json"))
    parser.add_argument("--split-scan", type=Path, required=True)
    parser.add_argument("--dividend-scan", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.private_queue,
                           args.price_parity_receipt, args.rules,
                           args.split_scan, args.dividend_scan),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

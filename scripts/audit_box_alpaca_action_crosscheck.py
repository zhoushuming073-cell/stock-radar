"""Crosscheck a private Alpaca announcement response against a pinned Dolt scan."""
from __future__ import annotations

import argparse
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path

from scripts.audit_box_free_event_exposure import parse_scan

VERSION = "box-alpaca-action-crosscheck-v1"
START, END = "2025-05-01", "2025-09-08"


def compare(announcements: list[dict], source: dict[tuple[str, str], list[dict]],
            symbols: set[str]) -> dict:
    seen: set[tuple[str, str]] = set()
    matched = 0
    for row in announcements:
        symbol, ex_date = row.get("symbol"), row.get("ex_date")
        key = (symbol, ex_date)
        if (not isinstance(symbol, str) or symbol not in symbols
                or not isinstance(ex_date, str) or len(ex_date) != 10
                or key in seen or row.get("corporate_action_type") != "cash_dividends"):
            raise ValueError("Alpaca event outside bounded comparison or duplicated")
        seen.add(key)
        hits = source.get(key, [])
        if len(hits) != 1:
            raise ValueError("Alpaca cash dividend lacks unique pinned-source match")
        if Decimal(str(hits[0]["amount"])) != Decimal(str(row.get("rate"))):
            raise ValueError("cross-source cash amount mismatch")
        matched += 1
    return {"alpaca_cash_events": len(announcements),
            "dolt_exact_symbol_exdate_amount_matches": matched}


def audit(root: Path, queue_path: Path, alpaca_path: Path,
          dividend_path: Path, event_receipt_path: Path) -> dict:
    root = root.resolve()
    paths = [queue_path.resolve(), alpaca_path.resolve(), dividend_path.resolve()]
    if any(not p.is_relative_to(root / "data") for p in paths):
        raise ValueError("source and cohort details must stay in ignored private data")
    queue_raw, alpaca_raw, dolt_raw, receipt_raw = (
        p.read_bytes() for p in (queue_path, alpaca_path,
                                dividend_path, event_receipt_path))
    queue, alpaca, receipt = (json.loads(raw) for raw in
                              (queue_raw, alpaca_raw, receipt_raw))
    rows = queue.get("rows", [])
    symbols = {r["symbol"] for r in rows}
    request = alpaca.get("request", {})
    groups = alpaca.get("announcements", {})
    if (len(rows) != 142 or len(symbols) != 28
            or queue.get("formal_lean_ready") is not False
            or receipt.get("private_queue_sha256") != sha256(queue_raw).hexdigest()
            or receipt.get("scan_sha256", {}).get("dividend")
            != sha256(dolt_raw).hexdigest()
            or receipt.get("formal_lean_ready") is not False
            or request.get("start") != START or request.get("end") != END
            or set(request.get("symbols", [])) != symbols
            or len(request.get("symbols", [])) != len(symbols)
            or request.get("limit", 0) < 1000
            or request.get("ca_types") is not None
            or not isinstance(groups, dict)
            or set(groups) - {"cash_dividends"}):
        raise ValueError("Alpaca request, cohort or pinned scan mismatch")
    _, source = parse_scan(dolt_raw, "dividend", receipt["event_source_version"],
                           "2023-12-12", "2025-09-22")
    totals = compare(groups.get("cash_dividends", []), source, symbols)
    for symbol, ex_date, amount in (("RYI", "2025-06-05", "0.1875"),
                                    ("NSA", "2025-06-13", "0.57")):
        hits = [r for r in groups.get("cash_dividends", [])
                if (r["symbol"], r["ex_date"]) == (symbol, ex_date)]
        if len(hits) != 1 or Decimal(str(hits[0]["rate"])) != Decimal(amount):
            raise ValueError("prior exposed event not corroborated by Alpaca")
    return {
        "version": VERSION, "split": "validation",
        "candidate_days": len(rows), "observed_symbols": len(symbols),
        "private_queue_sha256": sha256(queue_raw).hexdigest(),
        "private_alpaca_response_sha256": sha256(alpaca_raw).hexdigest(),
        "pinned_dolt_dividend_scan_sha256": sha256(dolt_raw).hexdigest(),
        "prior_event_receipt_sha256": sha256(receipt_raw).hexdigest(),
        **totals, "prior_exposed_cash_events_crosschecked": 2,
        "other_action_types_returned": 0,
        "complete_action_coverage_certified": False,
        "cash_entitlement_certified": False,
        "official_identity_certified": False,
        "future_outcomes_read": False, "formal_lean_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--private-queue", type=Path, required=True)
    parser.add_argument("--private-alpaca-response", type=Path, required=True)
    parser.add_argument("--dividend-scan", type=Path, required=True)
    parser.add_argument("--event-receipt", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.private_queue,
                           args.private_alpaca_response, args.dividend_scan,
                           args.event_receipt), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

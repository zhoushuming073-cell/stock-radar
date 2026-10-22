"""Aggregate later vendor lifecycle observations without T-time leakage."""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from scripts.audit_box_alpaca_action_crosscheck import START, END

VERSION = "box-later-lifecycle-observations-v1"


def observed_symbol(event: dict) -> str:
    kind = event.get("corporate_action_type")
    if kind in {"cash_mergers", "stock_mergers", "stock_and_cash_mergers"}:
        return event["acquiree_symbol"]
    if kind == "name_changes":
        return event["old_symbol"]
    return event["symbol"]


def summarize(queue: dict, short: dict, annual: dict) -> dict:
    rows = queue.get("rows", [])
    symbols = {r["symbol"] for r in rows}
    requests = ((short.get("request", {}), START, END),
                (annual.get("request", {}), "2025-01-01", "2025-12-31"))
    if (len(rows) != 142 or len(symbols) != 28
            or queue.get("formal_lean_ready") is not False):
        raise ValueError("frozen cohort mismatch")
    for request, start, end in requests:
        if (request.get("start") != start or request.get("end") != end
                or request.get("limit", 0) < 1000
                or request.get("ca_types") is not None
                or set(request.get("symbols", [])) != symbols
                or len(request.get("symbols", [])) != len(symbols)):
            raise ValueError("vendor request did not cover frozen symbol set")
    short_groups, annual_groups = (x.get("announcements", {})
                                   for x in (short, annual))
    if (not isinstance(short_groups, dict) or not isinstance(annual_groups, dict)):
        raise ValueError("missing vendor announcement groups")
    def keyed(groups: dict) -> dict[str, dict]:
        items = [row for group in groups.values() for row in group]
        ids = {row["id"]: row for row in items}
        if len(ids) != len(items):
            raise ValueError("duplicate vendor action ID")
        if any(observed_symbol(row) not in symbols for row in items):
            raise ValueError("vendor action outside cohort")
        return ids
    short_ids, annual_ids = keyed(short_groups), keyed(annual_groups)
    subset = {key: value for key, value in annual_ids.items()
              if START <= value["process_date"] <= END}
    if short_ids != subset:
        raise ValueError("year-wide and earlier process-date window disagree")
    noncash = [item for item in annual_ids.values()
               if item["corporate_action_type"] != "cash_dividends"]
    by_type = Counter(item["corporate_action_type"] for item in noncash)
    in_window = [item for item in noncash if item["process_date"] <= END]
    later = [item for item in noncash if item["process_date"] > END]
    later_symbols = {observed_symbol(item) for item in later}
    return {
        "short_process_window_events": len(short_ids),
        "annual_response_events": len(annual_ids),
        "annual_cash_dividends": len(annual_groups.get("cash_dividends", [])),
        "annual_noncash_by_type": dict(sorted(by_type.items())),
        "noncash_events_through_validation_end": len(in_window),
        "noncash_events_after_validation_end": len(later),
        "later_event_observed_symbols": len(later_symbols),
        "later_event_candidate_days": sum(r["symbol"] in later_symbols for r in rows),
    }


def audit(root: Path, queue_path: Path, short_path: Path,
          annual_path: Path, prior_receipt_path: Path) -> dict:
    root = root.resolve()
    private = [queue_path.resolve(), short_path.resolve(), annual_path.resolve()]
    if any(not path.is_relative_to(root / "data") for path in private):
        raise ValueError("details must stay in ignored private data")
    raw_queue, raw_short, raw_annual, raw_prior = (
        path.read_bytes() for path in (queue_path, short_path,
                                       annual_path, prior_receipt_path))
    prior = json.loads(raw_prior)
    if (prior.get("version") != "box-alpaca-action-crosscheck-v1"
            or prior.get("private_queue_sha256") != sha256(raw_queue).hexdigest()
            or prior.get("private_alpaca_response_sha256")
            != sha256(raw_short).hexdigest()
            or prior.get("formal_lean_ready") is not False):
        raise ValueError("prior vendor receipt mismatch")
    counts = summarize(*(json.loads(raw) for raw in
                         (raw_queue, raw_short, raw_annual)))
    return {"version": VERSION, "split": "validation",
            "private_queue_sha256": sha256(raw_queue).hexdigest(),
            "private_short_response_sha256": sha256(raw_short).hexdigest(),
            "private_annual_response_sha256": sha256(raw_annual).hexdigest(),
            "prior_receipt_sha256": sha256(raw_prior).hexdigest(),
            **counts, "retrospective_only": True,
            "used_in_t_time_selection": False,
            "complete_action_coverage_certified": False,
            "official_identity_certified": False,
            "future_outcomes_read": False, "formal_lean_ready": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--private-queue", type=Path, required=True)
    parser.add_argument("--private-short-response", type=Path, required=True)
    parser.add_argument("--private-annual-response", type=Path, required=True)
    parser.add_argument("--prior-receipt", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.private_queue,
                           args.private_short_response,
                           args.private_annual_response,
                           args.prior_receipt), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

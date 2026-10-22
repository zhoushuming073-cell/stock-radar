"""Aggregate private dated SEC class observations for a frozen box cohort.

The review rows are human-readable source observations. This script checks
their mapping and chronology; it does not certify the contents of the URLs or
prove a complete historical identity/lifecycle chain.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from urllib.parse import urlparse

from scripts.audit_box_cta_raw_gate_intersection import VERSION as QUEUE_VERSION

VERSION = "box-sec-class-observation-coverage-v1"


def check_review(row: dict, earliest: str, symbol: str, cik: str) -> None:
    if (row.get("symbol") != symbol or row.get("observed_cik") != cik
            or row.get("form") not in {"8-K", "10-K"}
            or "common" not in str(row.get("class_observed", "")).lower()
            or str(row.get("exchange_observed", "")).lower()
            not in {"nyse", "new york stock exchange", "the new york stock exchange"}):
        raise ValueError("review class/identity mapping mismatch")
    filing = row.get("filing_date")
    if (not isinstance(filing, str)
            or date.fromisoformat(filing).isoformat() != filing
            or filing >= earliest):
        raise ValueError("SEC observation was not available before earliest T")
    if row.get("earliest_candidate_date", earliest) != earliest:
        raise ValueError("review candidate-date mapping mismatch")
    parsed = urlparse(row.get("filing_url", ""))
    if (parsed.scheme != "https" or parsed.hostname != "www.sec.gov"
            or not parsed.path.startswith(
                f"/Archives/edgar/data/{int(cik)}/")
            or not parsed.path.endswith(".htm")):
        raise ValueError("review lacks exact-CIK SEC filing URL")


def audit(root: Path, queue_path: Path, parity_path: Path,
          review_paths: list[Path]) -> dict:
    root, queue_path = root.resolve(), queue_path.resolve()
    if not queue_path.is_relative_to(root / "data"):
        raise ValueError("private queue must remain under research-root/data")
    queue_raw = queue_path.read_bytes()
    queue = json.loads(queue_raw)
    parity = json.loads(parity_path.read_bytes())
    rows = queue.get("rows")
    if (queue.get("version") != QUEUE_VERSION or not isinstance(rows, list)
            or not rows or queue.get("formal_lean_ready") is not False
            or parity.get("private_queue_sha256") != sha256(queue_raw).hexdigest()
            or parity.get("candidate_days") != len(rows)
            or parity.get("formal_lean_ready") is not False):
        raise ValueError("private queue/price-parity receipt mismatch")
    cohort: dict[tuple[str, str], dict] = {}
    counts: Counter[tuple[str, str]] = Counter()
    seen_days: set[tuple[str, str]] = set()
    for row in rows:
        key = row["symbol"], row["observed_cik"]
        security_day = row["security_id"], row["decision_date"]
        if security_day in seen_days:
            raise ValueError("duplicate candidate day")
        seen_days.add(security_day)
        item = cohort.setdefault(key, {
            "security_id": row["security_id"],
            "earliest": row["decision_date"]})
        if item["security_id"] != row["security_id"]:
            raise ValueError("same observed CIK/symbol has multiple security IDs")
        item["earliest"] = min(item["earliest"], row["decision_date"])
        counts[key] += 1
    reviews = {}
    hashes = []
    for path in review_paths:
        resolved = path.resolve()
        if not resolved.is_relative_to(root / "data"):
            raise ValueError("SEC review must remain under research-root/data")
        raw = resolved.read_bytes()
        document = json.loads(raw)
        if (document.get("official_asof_t_identity_certified") is not False
                or document.get("formal_lean_ready") is not False
                or document.get("raw_filing_hashes_collected") is not False):
            raise ValueError("review claims an unsupported gate")
        for row in document["rows"]:
            if document.get("version") == "box-pre-t-sec-class-review-v1":
                row = {**row, "form": "10-K"}
            key = row["symbol"], row["observed_cik"]
            if key not in cohort or key in reviews:
                raise ValueError("review is absent from cohort or duplicated")
            check_review(row, cohort[key]["earliest"], *key)
            reviews[key] = row
        hashes.append(sha256(raw).hexdigest())
    observed_ids = {item["security_id"] for item in cohort.values()}
    return {
        "version": VERSION, "split": "validation",
        "private_queue_sha256": sha256(queue_raw).hexdigest(),
        "price_parity_receipt_sha256": sha256(parity_path.read_bytes()).hexdigest(),
        "private_review_sha256": sorted(hashes),
        "candidate_days": len(rows), "observed_security_ids": len(observed_ids),
        "reviewed_observed_security_ids": len(reviews),
        "reviewed_candidate_days": sum(counts[key] for key in reviews),
        "unreviewed_observed_security_ids": len(cohort) - len(reviews),
        "unreviewed_candidate_days": sum(counts[key] for key in cohort if key not in reviews),
        "dated_sec_class_observations_only": True,
        "filing_bytes_collected": False,
        "official_asof_t_identity_certified": False,
        "lifecycle_completeness_certified": False,
        "corporate_actions_certified": False,
        "future_outcomes_read": False,
        "formal_lean_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--private-queue", type=Path, required=True)
    parser.add_argument("--price-parity-receipt", type=Path, required=True)
    parser.add_argument("--private-review", type=Path, action="append", required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.private_queue,
                           args.price_parity_receipt, args.private_review),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

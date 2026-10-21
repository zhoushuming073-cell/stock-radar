"""Read-only, aggregate CTA symbol-snapshot overlap for sealed box candidates.

The CTA file is a *post-close reference*, not T-time signal input or an
issuer/share-class, corporate-action, or executable-price certificate.
Private candidate identities never enter the printed aggregate.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from hashlib import sha256
import json
from pathlib import Path

import duckdb

from radar.box_labeling.history import BoxHistory
from scripts.audit_box_candidate_execution_metadata import candidate_requests
from scripts.audit_box_candidate_issuer_at_t import build_windows
from scripts.audit_box_candidate_tday_price_bridge import (
    DOLT_SOURCE, accepted_database, compare_tday,
)
from scripts.audit_box_execution_horizon import HORIZON, horizon_metadata, summarize
from scripts.audit_box_range_issuer_alias_at_t import (
    classify, construction_source, dated_evidence,
)
from scripts.scan_box_near_lower_stage_d import execute
from scripts.summarize_box_candidate_gates import raw_complete

VERSION = "box-cta-symbol-coverage-v1"


def parse_cta(path: Path, day: str) -> dict[str, dict[str, str]]:
    if path.name != f"CTA.Symbol.File.{day.replace('-', '')}.csv":
        raise ValueError("CTA snapshot filename/date mismatch")
    rows: dict[str, dict[str, str]] = {}
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        reader = csv.DictReader(stream)
        required = {"Symbol", "PrimaryListingMarketParticipantID", "InstrumentType"}
        if not reader.fieldnames or not required.issubset(reader.fieldnames):
            raise ValueError("unexpected CTA symbol schema")
        for row in reader:
            # CTA symbols can differ only by case (for example TPC/TpC).
            # Folding case would silently merge distinct instruments.
            symbol = row["Symbol"].strip()
            if not symbol or symbol in rows:
                raise ValueError("missing or duplicate CTA symbol")
            rows[symbol] = row
    if not rows:
        raise ValueError("empty CTA symbol snapshot")
    return rows


def compare(requests: list[dict], symbols: dict[tuple[str, str, str], str],
            cta: dict[str, dict[str, str]]) -> dict:
    if len({r["security_id"] for r in requests}) != len(requests):
        raise ValueError("duplicate candidate security ID")
    if set(symbols) != {(r["security_id"], r["source"], r["basis"])
                        for r in requests}:
        raise ValueError("candidate/price symbol population differs")
    counts: Counter[tuple[str, str, str]] = Counter()
    markets: Counter[str] = Counter()
    instruments: Counter[str] = Counter()
    for request in requests:
        symbol = symbols[(request["security_id"], request["source"],
                          request["basis"])].strip()
        match = cta.get(symbol)
        status = "cta_symbol_present" if match else "cta_symbol_absent"
        counts[(request["source"], request["basis"], status)] += 1
        if match:
            markets[match["PrimaryListingMarketParticipantID"].strip()] += 1
            instruments[match["InstrumentType"].strip()] += 1
    return {
        "by_source_basis": [
            {"source": source, "basis": basis, "status": status, "rows": count}
            for (source, basis, status), count in sorted(counts.items())
        ],
        "matched_listing_market_codes": dict(sorted(markets.items())),
        "matched_instrument_type_codes": dict(sorted(instruments.items())),
    }


def raw_intersection(root: Path, provider: BoxHistory,
                     requests: list[dict], symbols: dict,
                     cta: dict, accepted_manifest: Path) -> tuple[dict, list[dict]]:
    """Keep every raw candidate, including CTA-absent rows, in the denominator."""
    raw = [r for r in requests if r["source"] == DOLT_SOURCE
           and r["basis"] == "raw"]
    if not raw:
        return {"raw_candidate_cross_tab": [], "raw_candidate_rows": 0}, []
    windows = build_windows(provider, raw)
    construction_path, construction_hash = construction_source(root)
    with duckdb.connect(str(construction_path), read_only=True) as source:
        issuer_rows = dated_evidence(source, windows)
    metadata = horizon_metadata(provider.api.core.connection, raw)
    horizon_rows, _ = summarize(raw, metadata)
    accepted_path, accepted = accepted_database(root, accepted_manifest)
    with duckdb.connect(str(accepted_path), read_only=True) as prices:
        tday = {r["task_id"]: compare_tday(provider.api.core.connection,
                                          prices, r["security_id"],
                                          r["decision_date"]) for r in raw}
    if (len(issuer_rows) != len(raw) or len(horizon_rows) != len(raw)
            or len(tday) != len(raw)):
        raise ValueError("raw candidate gate population drift")
    issuers = {r["task_id"]: r for r in issuer_rows}
    horizons = {r["task_id"]: r for r in horizon_rows}
    counts: Counter[tuple[str, str, str, str]] = Counter()
    private_followup = []
    for request in raw:
        task = request["task_id"]
        symbol = symbols[(request["security_id"], request["source"], "raw")]
        cta_status = "cta_present" if symbol in cta else "cta_absent"
        issuer_status = classify(issuers[task])
        horizon_complete = raw_complete(horizons[task], HORIZON)
        counts[(cta_status, issuer_status, tday[task],
                "raw_horizon_complete" if horizon_complete
                else "raw_horizon_incomplete")] += 1
        if (cta_status == "cta_present"
                and issuer_status == "OBSERVATIONAL_NO_KNOWN_CONFLICT"
                and tday[task] == "exact_tday_match" and horizon_complete):
            private_followup.append({
                "security_id": request["security_id"], "symbol": symbol,
                "observed_cik": issuers[task]["cik"],
                "decision_date": request["decision_date"],
                "issuer_status": issuer_status,
            })
    return {
        "raw_candidate_rows": len(raw),
        "construction_database_sha256": construction_hash,
        "accepted_database_sha256": accepted["database_sha256"],
        "diagnostic_horizon_sessions": HORIZON,
        "raw_candidate_cross_tab": [
            {"cta": cta_status, "issuer_observation": issuer,
             "accepted_tday_price": price, "raw_horizon": horizon,
             "rows": count}
            for (cta_status, issuer, price, horizon), count in sorted(counts.items())
        ],
    }, private_followup


def audit(root: Path, day: str, candidate_dir: Path, cta_path: Path,
          accepted_manifest: Path, detector_config: Path,
          context_config: Path, private_selection: Path | None = None) -> dict:
    root, candidate_dir = root.resolve(), candidate_dir.resolve()
    if not "2025-05-05" <= day <= "2025-09-08":
        raise ValueError("audit scoped to CTA-covered frozen Validation")
    if not candidate_dir.is_relative_to(root / "data"):
        raise ValueError("candidate files must be private under research-root/data")
    verified = execute(root, "validation", day, day, candidate_dir,
                       detector_config, context_config, verify_only=True)
    if not verified["complete"] or verified["missing_chunks"]:
        raise ValueError("candidate day incomplete")
    requests = candidate_requests(candidate_dir / "validation" / day,
                                  "validation", day)
    if len(requests) != verified["near_lower_union_rows"]:
        raise ValueError("candidate population drift")
    cta = parse_cta(cta_path, day)
    with BoxHistory(root) as provider:
        if provider.semantic_hash != verified["ri_semantic_hash"]:
            raise ValueError("frozen research semantics changed")
        ids = [r["security_id"] for r in requests]
        rows = provider.api.core.connection.execute(
            "SELECT security_id, source, basis, symbol FROM shape_price "
            "WHERE date = ? AND security_id IN (SELECT unnest(?))",
            [day, ids],
        ).fetchall() if ids else []
        wanted = {(r["security_id"], r["source"], r["basis"])
                  for r in requests}
        selected = [(security_id, source, basis, symbol)
                    for security_id, source, basis, symbol in rows
                    if (security_id, source, basis) in wanted]
        symbols = {(security_id, source, basis): symbol
                   for security_id, source, basis, symbol in selected}
        if len(symbols) != len(selected):
            raise ValueError("ambiguous candidate source/basis symbol mapping")
        overlap = compare(requests, symbols, cta)
        raw_gates, followup = raw_intersection(root, provider, requests,
                                               symbols, cta,
                                               accepted_manifest)
    if private_selection is not None:
        destination = private_selection.resolve()
        if not destination.is_relative_to(root / "data"):
            raise ValueError("private follow-up must remain under research-root/data")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as stream:
            json.dump({"version": VERSION, "decision_date": day,
                       "candidate_file_set_sha256": verified["verified_file_set_sha256"],
                       "cta_snapshot_sha256": sha256(cta_path.read_bytes()).hexdigest(),
                       "rows": followup, "formal_lean_ready": False},
                      stream, ensure_ascii=False, indent=2)
    return {
        "version": VERSION, "split": "validation", "decision_date": day,
        "candidate_file_set_sha256": verified["verified_file_set_sha256"],
        "ri_semantic_hash": verified["ri_semantic_hash"],
        "cta_snapshot_sha256": sha256(cta_path.read_bytes()).hexdigest(),
        "cta_snapshot_rows": len(cta), "candidate_rows": len(requests),
        **overlap, **raw_gates,
        "private_followup_rows": len(followup),
        "source_scope": "CTA post-close symbol snapshot only",
        "identity_class_certified": False,
        "corporate_actions_certified": False,
        "execution_prices_certified": False,
        "known_by_decision_close": False,
        "future_ohlcv_read": False,
        "future_outcomes_read": False,
        "formal_lean_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--day", required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--cta-file", type=Path, required=True)
    parser.add_argument("--accepted-manifest", type=Path, required=True)
    parser.add_argument("--private-selection", type=Path)
    parser.add_argument("--detector-config", type=Path,
                        default=Path("config/box_range_detector_stage_a_v1.yaml"))
    parser.add_argument("--context-config", type=Path,
                        default=Path("config/box_lower_band_context_v1.yaml"))
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.day, args.candidate_dir,
                           args.cta_file, args.accepted_manifest,
                           args.detector_config,
                           args.context_config, args.private_selection),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

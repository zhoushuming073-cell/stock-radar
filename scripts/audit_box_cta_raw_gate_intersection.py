"""Intersect CTA-covered Validation raw candidates with existing data gates.

The ten-session horizon is a coverage diagnostic, not a holding rule. Post-T
queries read metadata only; no future OHLCV values or returns are selected.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import duckdb

from radar.box_labeling.history import BoxHistory
from scripts.audit_box_candidate_accepted_horizon import accepted_session_metadata
from scripts.audit_box_candidate_execution_metadata import candidate_requests
from scripts.audit_box_candidate_issuer_at_t import build_windows
from scripts.audit_box_candidate_tday_price_bridge import (
    DOLT_SOURCE, accepted_database, compare_tday,
)
from scripts.audit_box_cta_full_coverage import (
    START, END, audit as full_cta_audit,
)
from scripts.audit_box_cta_symbol_coverage import parse_cta
from scripts.audit_box_execution_horizon import HORIZON, horizon_metadata, summarize
from scripts.audit_box_range_issuer_alias_at_t import (
    classify, construction_source, dated_evidence,
)
from scripts.summarize_box_candidate_gates import raw_complete

VERSION = "box-cta-raw-gate-intersection-v1"


def cta_matched_raw_requests(provider: BoxHistory, candidate_dir: Path,
                             cta_dir: Path) -> list[dict]:
    selected = []
    for folder in sorted((candidate_dir / "validation").iterdir()):
        day = folder.name
        if not folder.is_dir() or not START <= day <= END:
            continue
        cta = parse_cta(cta_dir / f"CTA.Symbol.File.{day.replace('-', '')}.csv", day)
        raw = [r for r in candidate_requests(folder, "validation", day)
               if r["source"] == DOLT_SOURCE and r["basis"] == "raw"]
        if not raw:
            continue
        ids = [r["security_id"] for r in raw]
        rows = provider.api.core.connection.execute(
            "SELECT security_id,symbol FROM shape_price "
            "WHERE date=? AND source=? AND basis='raw' "
            "AND security_id IN (SELECT unnest(?))",
            [day, DOLT_SOURCE, ids],
        ).fetchall()
        symbols = dict(rows)
        if len(rows) != len(symbols) or set(symbols) != set(ids):
            raise ValueError("raw candidate/symbol mapping drift")
        selected.extend({**request, "symbol": symbols[request["security_id"]]}
                        for request in raw
                        if symbols[request["security_id"]] in cta)
    return selected


def audit(root: Path, candidate_dir: Path, cta_dir: Path,
          accepted_manifest: Path, detector_config: Path,
          context_config: Path, private_queue: Path | None = None) -> dict:
    root, candidate_dir, cta_dir = (path.resolve()
                                    for path in (root, candidate_dir, cta_dir))
    full = full_cta_audit(root, candidate_dir, cta_dir,
                          detector_config, context_config)
    accepted_path, accepted_manifest_data = accepted_database(root, accepted_manifest)
    construction_path, construction_hash = construction_source(root)
    with BoxHistory(root) as provider:
        if provider.semantic_hash != full["ri_semantic_hash"]:
            raise ValueError("frozen research semantics changed")
        selected = cta_matched_raw_requests(provider, candidate_dir, cta_dir)
        expected = sum(row["rows"] for row in full["source_basis_status"]
                       if row["source"] == DOLT_SOURCE and row["basis"] == "raw"
                       and row["status"] == "cta_symbol_present")
        if len(selected) != expected or len({r["task_id"] for r in selected}) != expected:
            raise ValueError("CTA/raw candidate population drift")
        windows = build_windows(provider, selected)
        metadata = horizon_metadata(provider.api.core.connection, selected)
        horizon_rows, _ = summarize(selected, metadata)
        with duckdb.connect(str(construction_path), read_only=True) as construction:
            issuer_rows = dated_evidence(construction, windows)
        if len(issuer_rows) != expected or len(horizon_rows) != expected:
            raise ValueError("issuer/horizon population drift")
        issuers = {row["task_id"]: row for row in issuer_rows}
        horizons = {row["task_id"]: row for row in horizon_rows}
        counts: Counter[tuple[str, str, str, str]] = Counter()
        queue = []
        with duckdb.connect(str(accepted_path), read_only=True) as accepted:
            for request in selected:
                task, sid, day = (request[key] for key in
                                  ("task_id", "security_id", "decision_date"))
                issuer = classify(issuers[task])
                shape_raw = raw_complete(horizons[task], HORIZON)
                tday = compare_tday(provider.api.core.connection, accepted, sid, day)
                accepted_horizon = "not_checked_tday_inexact"
                if tday == "exact_tday_match":
                    sessions = [row["date"] for row in horizons[task]["sessions"]]
                    metadata_counts = accepted_session_metadata(
                        accepted, sid, sessions, request["symbol"])
                    accepted_horizon = (
                        "accepted_metadata_complete"
                        if len(sessions) == HORIZON
                        and metadata_counts.get("matching_raw", 0) == HORIZON
                        and metadata_counts.get("symbol_transition", 0) == 0
                        else "accepted_metadata_incomplete")
                counts[(issuer,
                        "shape_raw_complete" if shape_raw else "shape_raw_incomplete",
                        tday, accepted_horizon)] += 1
                if (issuer == "OBSERVATIONAL_NO_KNOWN_CONFLICT"
                        and shape_raw and tday == "exact_tday_match"
                        and accepted_horizon == "accepted_metadata_complete"):
                    queue.append({"security_id": sid, "symbol": request["symbol"],
                                  "decision_date": day,
                                  "observed_cik": issuers[task]["cik"]})
    if private_queue is not None:
        destination = private_queue.resolve()
        if not destination.is_relative_to(root / "data"):
            raise ValueError("private queue must remain under research-root/data")
        destination.parent.mkdir(parents=True, exist_ok=True)
        with destination.open("x", encoding="utf-8") as stream:
            json.dump({"version": VERSION,
                       "candidate_file_set_sha256": full["candidate_file_set_sha256"],
                       "rows": queue, "formal_lean_ready": False},
                      stream, ensure_ascii=False, indent=2)
    return {
        "version": VERSION, "split": "validation", "start": START, "end": END,
        "candidate_file_set_sha256": full["candidate_file_set_sha256"],
        "cta_snapshot_file_count": len(full["cta_snapshot_hashes"]),
        "ri_semantic_hash": full["ri_semantic_hash"],
        "construction_database_sha256": construction_hash,
        "accepted_database_sha256": accepted_manifest_data["database_sha256"],
        "cta_matched_dolt_raw_candidate_days": expected,
        "gate_cross_tab": [
            {"issuer_observation": issuer, "shape_raw_horizon": shape,
             "accepted_tday": tday, "accepted_horizon": accepted_horizon,
             "rows": count}
            for (issuer, shape, tday, accepted_horizon), count in sorted(counts.items())
        ],
        "private_followup_candidate_days": len(queue),
        "private_followup_observed_security_ids": len({r["security_id"] for r in queue}),
        "horizon_sessions_diagnostic_only": HORIZON,
        "future_price_values_read": False, "future_outcomes_read": False,
        "official_identity_certified": False,
        "corporate_actions_certified": False,
        "execution_prices_certified": False,
        "formal_lean_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--cta-dir", type=Path, required=True)
    parser.add_argument("--accepted-manifest", type=Path, required=True)
    parser.add_argument("--private-queue", type=Path)
    parser.add_argument("--detector-config", type=Path,
                        default=Path("config/box_range_detector_stage_a_v1.yaml"))
    parser.add_argument("--context-config", type=Path,
                        default=Path("config/box_lower_band_context_v1.yaml"))
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.candidate_dir, args.cta_dir,
                           args.accepted_manifest, args.detector_config,
                           args.context_config, args.private_queue),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

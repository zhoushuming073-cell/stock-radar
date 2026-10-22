"""Aggregate all public CTA-covered frozen Validation box candidate days.

Post-close CTA snapshots only corroborate exact-case historical symbols.
This audit never promotes identity, actions, raw execution prices or signals.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from radar.box_labeling.history import BoxHistory
from radar.box_labeling.stage_b import digest, packed
from scripts.audit_box_candidate_execution_metadata import candidate_requests
from scripts.audit_box_cta_symbol_coverage import compare, parse_cta
from scripts.scan_box_near_lower_stage_d import execute

VERSION = "box-cta-full-covered-validation-v1"
START, END = "2025-05-05", "2025-09-08"


def audit(root: Path, candidate_dir: Path, cta_dir: Path,
          detector_config: Path, context_config: Path) -> dict:
    root, candidate_dir, cta_dir = (path.resolve()
                                    for path in (root, candidate_dir, cta_dir))
    if (not candidate_dir.is_relative_to(root / "data")
            or not cta_dir.is_relative_to(root / "data")):
        raise ValueError("candidate and CTA files must stay in private local data")
    verified = execute(root, "validation", START, END, candidate_dir,
                       detector_config, context_config, verify_only=True)
    if not verified["complete"] or verified["missing_chunks"]:
        raise ValueError("candidate interval not fully verified")
    folders = [path for path in sorted((candidate_dir / "validation").iterdir())
               if path.is_dir() and START <= path.name <= END]
    if len(folders) != verified["sessions"]:
        raise ValueError("candidate session count drift")
    hashes: list[str] = []
    totals: Counter[tuple[str, str, str]] = Counter()
    markets: Counter[str] = Counter()
    instruments: Counter[str] = Counter()
    cta_hashes = []
    candidate_rows = 0
    with BoxHistory(root) as provider:
        if provider.semantic_hash != verified["ri_semantic_hash"]:
            raise ValueError("frozen research semantics changed")
        for folder in folders:
            day = folder.name
            files = sorted(folder.glob("*.json"))
            hashes.extend(sha256(path.read_bytes()).hexdigest() for path in files)
            requests = candidate_requests(folder, "validation", day)
            candidate_rows += len(requests)
            cta_path = cta_dir / f"CTA.Symbol.File.{day.replace('-', '')}.csv"
            cta = parse_cta(cta_path, day)
            cta_hashes.append({"date": day,
                               "sha256": sha256(cta_path.read_bytes()).hexdigest()})
            ids = [r["security_id"] for r in requests]
            rows = provider.api.core.connection.execute(
                "SELECT security_id,source,basis,symbol FROM shape_price "
                "WHERE date=? AND security_id IN (SELECT unnest(?))",
                [day, ids],
            ).fetchall() if ids else []
            wanted = {(r["security_id"], r["source"], r["basis"])
                      for r in requests}
            selected = [(sid, source, basis, symbol)
                        for sid, source, basis, symbol in rows
                        if (sid, source, basis) in wanted]
            symbols = {(sid, source, basis): symbol
                       for sid, source, basis, symbol in selected}
            if len(selected) != len(symbols):
                raise ValueError("ambiguous source/basis symbol mapping")
            compared = compare(requests, symbols, cta)
            totals.update({(row["source"], row["basis"], row["status"]):
                           row["rows"] for row in compared["by_source_basis"]})
            markets.update(compared["matched_listing_market_codes"])
            instruments.update(compared["matched_instrument_type_codes"])
    if (candidate_rows != verified["near_lower_union_rows"]
            or len(hashes) != verified["verified_chunks"]
            or digest(packed(hashes)) != verified["verified_file_set_sha256"]):
        raise ValueError("verified candidate file set changed during CTA audit")
    return {
        "version": VERSION, "split": "validation", "start": START, "end": END,
        "sessions": len(folders), "candidate_rows": candidate_rows,
        "candidate_chunks": len(hashes),
        "candidate_file_set_sha256": verified["verified_file_set_sha256"],
        "ri_semantic_hash": verified["ri_semantic_hash"],
        "cta_snapshot_hashes": cta_hashes,
        "source_basis_status": [
            {"source": source, "basis": basis, "status": status, "rows": count}
            for (source, basis, status), count in sorted(totals.items())
        ],
        "matched_listing_market_codes": dict(sorted(markets.items())),
        "matched_instrument_type_codes": dict(sorted(instruments.items())),
        "cta_symbol_present": sum(count for (_, _, status), count in totals.items()
                                  if status == "cta_symbol_present"),
        "source_scope": "CTA post-close symbol snapshot only",
        "known_by_decision_close": False,
        "identity_class_certified": False,
        "corporate_actions_certified": False,
        "execution_prices_certified": False,
        "future_ohlcv_read": False,
        "future_outcomes_read": False,
        "formal_lean_ready": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--cta-dir", type=Path, required=True)
    parser.add_argument("--detector-config", type=Path,
                        default=Path("config/box_range_detector_stage_a_v1.yaml"))
    parser.add_argument("--context-config", type=Path,
                        default=Path("config/box_lower_band_context_v1.yaml"))
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.candidate_dir,
                           args.cta_dir, args.detector_config,
                           args.context_config), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

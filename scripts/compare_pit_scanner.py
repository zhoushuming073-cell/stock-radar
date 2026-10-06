"""Frozen-strategy causal selection witnesses, without forward performance.

Consumes the production Scanner on pinned dates from the coverage audit. The
one-date evaluation calendar intentionally supplies no future labels. This is
not a portfolio comparison or an estimate of unbiased investment returns.
"""
import argparse
import hashlib
import json
from pathlib import Path

import pandas as pd

from radar.lab.data import MARKET_FEATURES, available_features, load_forward_bars, load_strategy_segment
from radar.lab.scanner import evaluation_settings
from radar.lab.scanner_worker import scan_frames
from radar.lab.universe import LocalSecurityMaster
from radar.pit.features import file_hash
from radar.strategy.loader import load_strategy_directory


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--database", type=Path, default=Path("data/phase2-research.duckdb"))
    p.add_argument("--strategy", type=Path, default=Path("strategies/full_strategy2_v1"))
    p.add_argument("--reports", type=Path)
    args = p.parse_args()
    master = LocalSecurityMaster(args.build / "security-master.csv", args.build / "security-master-manifest.json")
    output = args.reports or Path("data/pit/reports") / master.manifest["source_version"]
    dates = json.loads((output / "current-vs-pit.json").read_text(encoding="utf-8"))
    registration = load_strategy_directory(args.strategy, available_features(args.database), run_tests=True)
    required = set(registration.manifest.required_features) | MARKET_FEATURES
    original_hash = file_hash(args.database)
    records = []
    for item in dates:
        if "date" not in item:
            continue
        day = pd.Timestamp(item["date"])
        baseline = load_strategy_segment(args.database, day, day, required)
        pit = load_strategy_segment(args.database, day, day, required, master)
        # Only the signal day's OHLC is provided. The production selection
        # path runs; the evaluation layer cannot inspect subsequent sessions.
        bars = load_forward_bars(args.database, day, day)
        current_rows, current_metrics = scan_frames(registration.plugin, registration.config,
            baseline, bars, pd.DatetimeIndex([day]), day, day, evaluation_settings(None))
        pit_rows, pit_metrics = scan_frames(registration.plugin, registration.config,
            pit, bars, pd.DatetimeIndex([day]), day, day, evaluation_settings(None), universe_provider=master)
        current = {r["symbol"] for r in current_rows if r["selected"]}
        selected = {r["symbol"] for r in pit_rows if r["selected"]}
        record = {"date": str(day.date()), "pit_membership": len(master.eligible_on(day)),
            "pit_with_available_features": len(pit), "current_with_available_features": len(baseline),
            "current_selected": len(current), "pit_selected": len(selected),
            "candidate_intersection": len(current & selected), "pit_only_candidates": sorted(selected - current),
            "current_only_candidates": sorted(current - selected), "current_candidates": sorted(current),
            "pit_candidates": sorted(selected), "pit_candidate_security_ids": {r["symbol"]: r["security_id"] for r in pit_rows if r["selected"]},
            "current_funnel": current_metrics["funnel_by_day"], "pit_funnel": pit_metrics["funnel_by_day"],
            "future_labels_evaluated": False}
        records.append(record)
        print(json.dumps({key: record[key] for key in ("date", "pit_membership", "pit_with_available_features",
                                                       "current_selected", "pit_selected", "candidate_intersection")}), flush=True)
    if file_hash(args.database) != original_hash:
        raise ValueError("comparison source research database changed")
    manifest = {"strategy_id": registration.manifest.id, "strategy_version": registration.manifest.version,
        "strategy_code_sha256": file_hash(args.strategy / "strategy.py"),
        "strategy_config_sha256": file_hash(args.strategy / "strategy.yaml"),
        "source_research_sha256": original_hash, "universe_fingerprint": master.fingerprint,
        "universe_version": master.manifest["source_version"], "feature_store": master.feature_store,
        "selection_implementation": "radar.lab.scanner_worker.scan_frames -> production plugin adapter",
        "strategy_or_thresholds_changed": False, "future_performance_examined": False,
        "lean_comparison": "blocked: PIT corporate actions and terminal economics remain unvalidated",
        "interpretation": "differences include historical membership, product-type filtering, identity warm-up and daily population ranks; not an isolated causal estimate of survivorship bias",
        "dates": records}
    (output / "scanner-selection-comparison.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()

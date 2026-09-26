"""Compare the migrated plugin with the immutable Phase 2 Strategy 2 artifacts.

This script never writes the saved oracle files or runs parameter research.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from radar.backtest.costs import load_fee_config
from radar.backtest.engine import run_backtest
from radar.backtest.full_strategy2_runner import _full_rules, load_full_segment
from radar.backtest.runner import _engine_config, _rules, load_backtest_config, split_dates
from radar.strategy.adapter import make_candidate_selector
from radar.strategy.full_strategy2 import rank_full_strategy2
from radar.strategy.loader import load_strategy_directory


def verify(root: Path, splits: tuple[str, ...]) -> dict:
    root = root.resolve()
    database = root / "data" / "phase2-research.duckdb"
    oracle = root / "data" / "research" / "full-strategy2-v1"
    rules, full_raw = _full_rules(root / "config" / "full_strategy2.yaml")
    backtest_raw = load_backtest_config(root / "config" / "backtest.yaml")
    fees = load_fee_config(root / "config" / "research.yaml")
    split = split_dates(database, root / "config" / "research.yaml")
    registration = load_strategy_directory(
        root / "strategies" / "full_strategy2_v1",
        available_features=set(load_full_segment(database, split["train"][0], split["train"][0]).columns),
        run_tests=True,
    )
    selector = make_candidate_selector(registration.plugin, registration.config)
    report: dict[str, dict] = {}
    for name in splits:
        dates = split[name]
        frame = load_full_segment(database, dates[0], dates[2])
        available_dates = set(frame.index.get_level_values("date").unique())
        signal_dates = [date for date in split["sessions"]
                        if dates[0] <= date <= dates[1] and date in available_dates]
        signals_checked = 0
        for date in signal_dates:
            daily = frame.xs(date, level="date", drop_level=True).set_index("symbol", drop=False)
            old = rank_full_strategy2(daily, rules, already_held=set())
            new = selector(daily, set())
            old_rows = [(row.symbol, float(row.strategy2_score)) for row in old.itertuples(index=False)]
            new_rows = [(row.symbol, float(row.strategy2_score)) for row in new.itertuples(index=False)]
            if old_rows != new_rows:
                raise AssertionError(f"signal parity failed on {name} {date.date()}: {old_rows} != {new_rows}")
            signals_checked += 1
        config = _engine_config(
            backtest_raw, variant="full_strategy2", allocator=full_raw["allocator"],
            slippage_bps=float(full_raw["base_slippage_bps"]),
            max_position_fraction=float(backtest_raw["max_position_fraction"]),
        )
        result = run_backtest(
            frame, split["sessions"], signal_start=dates[0], signal_end=dates[1],
            evaluation_end=dates[2], rules=_rules(backtest_raw), fee_config=fees,
            config=config, candidate_selector=selector,
        )
        counts = {}
        for key, actual in (("equity", result.equity), ("trades", result.trades), ("orders", result.orders)):
            expected = (oracle / f"{name}_{key}.csv").read_text(encoding="utf-8-sig").replace("\r\n", "\n")
            produced = actual.to_csv(index=False, lineterminator="\n")
            if produced != expected:
                raise AssertionError(f"saved {name}_{key}.csv differs from plugin output")
            counts[key] = len(actual)
        report[name] = {"signal_dates_checked": signals_checked, "saved_artifact_rows": counts,
                        "exact_csv_parity": True}
        print(f"{name}: {signals_checked} signal dates; equity/trades/orders exact", flush=True)
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--splits", nargs="+", choices=["train", "validation", "test"],
                        default=["train", "validation", "test"])
    args = parser.parse_args()
    print(json.dumps(verify(args.root, tuple(args.splits)), indent=2))

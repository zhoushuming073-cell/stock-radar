"""Small prespecified market-regime and concentration sensitivity on Train/Validation."""

from pathlib import Path

import pandas as pd

from radar.backtest.costs import load_fee_config
from radar.backtest.runner import (load_backtest_config, load_segment,
                                   load_spy_ma200_guard, run_one_segment, split_dates)


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    db = ROOT / "data" / "phase2-research.duckdb"
    research = ROOT / "config" / "research.yaml"
    backtest = ROOT / "config" / "backtest.yaml"
    raw = load_backtest_config(backtest)
    fees = load_fee_config(research)
    split = split_dates(db, research)
    rows = []
    for name in ("train", "validation"):
        dates = split[name]
        frame = load_segment(db, dates[0], dates[2])
        guard = load_spy_ma200_guard(db, dates[2])
        for variant in ("drawdown_rank", "combined_rank"):
            for market_guard in ("none", "spy_ma200"):
                for cap in (.25, 1 / 3):
                    _, metrics = run_one_segment(
                        frame, dates, split["sessions"], raw, fees,
                        variant=variant, allocator="equal_cash",
                        slippage_bps=10, max_position_fraction=cap,
                        market_guard=market_guard, market_ok=guard)
                    rows.append({"split": name, "candidate_variant": variant,
                                 "market_guard": market_guard, "max_position_fraction": cap,
                                 **{key: value for key, value in metrics.items()
                                    if not isinstance(value, dict)}})
    target = ROOT / "data" / "research" / "backtest-v1" / "market_guard_grid.csv"
    pd.DataFrame(rows).to_csv(target, index=False)
    print(target)


if __name__ == "__main__":
    main()

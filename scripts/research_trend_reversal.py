"""Research the human-specified trend/pullback/reversal shape on Train/Validation."""

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
        for market_guard in ("none", "spy_ma200"):
            for allocator in ("equal_cash", "strategy_score"):
                result, metrics = run_one_segment(
                    frame, dates, split["sessions"], raw, fees,
                    variant="trend_reversal", allocator=allocator,
                    slippage_bps=10, max_position_fraction=1 / 3,
                    market_guard=market_guard, market_ok=guard)
                rows.append({"split": name, "market_guard": market_guard,
                             "allocator": allocator,
                             **{key: value for key, value in metrics.items()
                                if not isinstance(value, dict)}})
                if market_guard == "none" and allocator == "equal_cash":
                    out = ROOT / "data" / "research" / "backtest-v1"
                    result.trades.to_csv(out / f"{name}_trend_reversal_trades.csv", index=False)
                    result.equity.to_csv(out / f"{name}_trend_reversal_equity.csv", index=False)
    target = ROOT / "data" / "research" / "backtest-v1" / "trend_reversal_grid.csv"
    pd.DataFrame(rows).to_csv(target, index=False)
    print(target)


if __name__ == "__main__":
    main()

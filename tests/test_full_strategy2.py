from pathlib import Path

import pandas as pd
import pytest

from radar.backtest.costs import load_fee_config
from radar.backtest.engine import BacktestConfig, run_backtest
from radar.strategy.full_strategy2 import (
    FullStrategy2Rules, rank_full_strategy2, score_full_strategy2,
)
from radar.strategy.ranking import CandidateRules


def signal(symbol="A"):
    return {
        "symbol": symbol, "security_name": f"{symbol} Inc",
        "tradability_pass": True, "elasticity_score": 85.0,
        "ret_60": .10, "drawdown_60": -.30,
        "drawdown_20": -.20, "pullback_days_20": 5,
        "decline_speed_prev_3": -.10, "decline_acceleration": .08,
        "red_body_avg_3": .01, "red_body_avg_5": .03,
        "range_contraction": .8, "volume_contraction": .7,
        "lower_wick_ratio": .35, "close_location": .8,
        "failed_breakdown": False, "support_reclaim": False,
        "new_low_frequency_5": 0.0, "higher_low_proxy": True,
        "ret_1": .02, "body_pct": .03, "reclaim_ma_5": True,
        "rebound_from_low_5": .05, "dist_ma_5": -.02,
        "close": 100., "avg_dollar_volume_20": 1e9,
    }


def test_complete_lifecycle_requires_strength_reversal_and_no_extension():
    rows = [signal("PASS"), signal("NO_STRENGTH"), signal("NO_REVERSAL"),
            signal("EXTENDED"), signal("FUND")]
    rows[1]["ret_60"] = -.70
    rows[2]["ret_1"] = -.02
    rows[2]["body_pct"] = -.03
    rows[3]["rebound_from_low_5"] = .30
    rows[4]["security_name"] = "Example ETF"
    frame = pd.DataFrame(rows)
    scored = score_full_strategy2(frame, FullStrategy2Rules())
    assert scored.loc[scored.symbol == "PASS", "strategy2_eligible"].iloc[0]
    assert set(scored.loc[scored.strategy2_eligible, "symbol"]) == {"PASS", "FUND"}
    renamed = frame.copy()
    renamed["security_name"] = "Future ETF name"
    replay = score_full_strategy2(renamed, FullStrategy2Rules())
    assert replay["strategy2_eligible"].tolist() == scored["strategy2_eligible"].tolist()
    assert replay["strategy2_score"].tolist() == scored["strategy2_score"].tolist()
    assert scored.loc[0, "prior_peak_gain_60"] > .13
    assert frame.columns.isin(["strategy2_score"]).sum() == 0


def test_missing_causal_feature_fails_instead_of_silent_proxy():
    with pytest.raises(ValueError, match="decline_acceleration"):
        score_full_strategy2(pd.DataFrame([signal()]).drop(columns="decline_acceleration"),
                             FullStrategy2Rules())


def test_ranking_is_deterministic_and_ignores_future_label():
    rows = [signal(name) for name in ["C", "B", "D", "A"]]
    frame = pd.DataFrame(rows).set_index("symbol", drop=False)
    selected = rank_full_strategy2(frame, FullStrategy2Rules(), already_held={"A"})
    assert selected.symbol.tolist() == ["B", "C", "D"]
    frame["future_return"] = [-.99, .99, -.99, .99]
    again = rank_full_strategy2(frame, FullStrategy2Rules(), already_held={"A"})
    assert again.symbol.tolist() == selected.symbol.tolist()


def test_full_selector_enters_at_next_session_open():
    days = list(pd.bdate_range("2025-01-01", periods=12))
    rows = []
    for idx, day in enumerate(days):
        row = signal()
        row.update(date=day, open=100. if idx != 1 else 102.,
                   close=100. if idx != 1 else 108.)
        rows.append(row)
    frame = pd.DataFrame(rows).set_index(["date", "symbol"], drop=False)
    fees = load_fee_config(Path(__file__).parents[1] / "config" / "research.yaml")
    full_rules = FullStrategy2Rules()
    result = run_backtest(
        frame, days, signal_start=days[0], signal_end=days[0],
        evaluation_end=days[10], rules=CandidateRules(0, 0, 3),
        fee_config=fees,
        config=BacktestConfig(slippage_bps=0, max_position_fraction=1,
                              max_order_to_avg_dollar_volume=1),
        candidate_selector=lambda daily, held: rank_full_strategy2(
            daily, full_rules, already_held=held),
    )
    assert result.trades.iloc[0].entry_date == days[1]
    assert result.trades.iloc[0].entry_reference == 102.

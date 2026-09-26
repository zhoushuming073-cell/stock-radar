"""Tests for the example interface; run with Stock Radar on PYTHONPATH."""

import pandas as pd

from radar.strategy.context import StrategyContext
from strategy import PLUGIN


CONFIG = {
    "prior_strength": {"min_return_60": 0.15},
    "pullback": {"min_depth": 0.08, "max_depth": 0.30},
    "selection": {"max_candidates": 3},
}


def _context() -> StrategyContext:
    frame = pd.DataFrame(
        {
            "symbol": ["BBB", "AAA", "CCC", "DDD"],
            "security_name": ["B", "A", "C", "D"],
            "close": [10.0, 20.0, 30.0, 40.0],
            "tradability_pass": [True, True, False, True],
            "ret_60": [0.20, 0.20, 0.30, float("nan")],
            "drawdown_20": [-0.15, -0.15, -0.15, -0.15],
        }
    )
    return StrategyContext(signal_date=pd.Timestamp("2024-01-02"), frame=frame)


def test_filter_and_score_align_with_context():
    context = _context()
    eligible = PLUGIN.hard_filter(context, CONFIG)
    score = PLUGIN.score(context, CONFIG)
    assert eligible.dtype == bool
    assert eligible.index.equals(context.frame.index)
    assert eligible.tolist() == [True, True, False, False]
    assert score.index.equals(context.frame.index)
    assert score.iloc[0] == 0.20


def test_select_is_stable_and_keeps_only_eligible_rows():
    context = _context()
    frame = context.frame
    eligible = PLUGIN.hard_filter(context, CONFIG)
    candidates = frame.loc[eligible].copy()
    candidates["strategy_score"] = PLUGIN.score(context, CONFIG).loc[eligible]
    first = PLUGIN.select(candidates, CONFIG)
    second = PLUGIN.select(candidates, CONFIG)
    assert first["symbol"].tolist() == ["AAA", "BBB"]
    pd.testing.assert_frame_equal(first, second)
    assert PLUGIN.select(candidates.iloc[0:0], CONFIG).empty


def test_thresholds_are_configurable_without_code_change():
    config = {
        **CONFIG,
        "prior_strength": {"min_return_60": 0.21},
    }
    assert not PLUGIN.hard_filter(_context(), config).any()


def test_only_declared_causal_features_are_needed():
    assert PLUGIN.required_features() == {
        "tradability_pass", "ret_60", "drawdown_20"
    }

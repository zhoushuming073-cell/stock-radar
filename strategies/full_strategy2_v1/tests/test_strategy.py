import pandas as pd

from radar.strategy.context import StrategyContext
from strategy import PLUGIN


CONFIG = {
    "max_new": 3,
    "min_elasticity": 76.21433772581146,
    "min_prior_peak_gain": 0.13230715023626216,
    "min_pullback": 0.08,
    "max_pullback": 0.40,
    "max_new_low_frequency_5": 0.20,
    "max_rebound_from_5d_low": 0.15,
    "max_one_day_return": 0.10,
    "max_distance_from_ma5": 0.15,
    "min_close_location": 0.50,
    "min_wick_ratio": 0.25,
    "max_volume_contraction": 0.80,
    "exclude_explicit_funds": False,
}


def test_official_plugin_preserves_phase2_ranking():
    rows = []
    for symbol in ("C", "B", "A", "FUND"):
        row = {
            "symbol": symbol, "security_name": "Example ETF" if symbol == "FUND" else f"{symbol} Inc",
            "tradability_pass": True, "elasticity_score": 85., "ret_60": .10,
            "drawdown_60": -.30, "drawdown_20": -.20, "pullback_days_20": 5,
            "decline_speed_prev_3": -.10, "decline_acceleration": .08,
            "red_body_avg_3": .01, "red_body_avg_5": .03, "range_contraction": .8,
            "volume_contraction": .7, "lower_wick_ratio": .35, "close_location": .8,
            "failed_breakdown": False, "support_reclaim": False,
            "new_low_frequency_5": 0., "higher_low_proxy": True,
            "ret_1": .02, "body_pct": .03, "reclaim_ma_5": True,
            "rebound_from_low_5": .05, "dist_ma_5": -.02,
            "close": 100., "avg_dollar_volume_20": 1e9,
        }
        rows.append(row)
    frame = pd.DataFrame(rows)
    context = StrategyContext(pd.Timestamp("2025-01-02"), frame)
    mask = PLUGIN.hard_filter(context, CONFIG)
    scores = PLUGIN.score(context, CONFIG)
    assert mask.tolist() == [True, True, True, True]
    renamed = frame.assign(security_name="Future ETF")
    assert PLUGIN.hard_filter(StrategyContext(pd.Timestamp("2025-01-02"), renamed),
                              CONFIG).tolist() == mask.tolist()
    candidates = frame.loc[mask].copy()
    candidates["strategy_score"] = scores.loc[mask]
    assert PLUGIN.select(candidates, CONFIG)["symbol"].tolist() == ["A", "B", "C"]

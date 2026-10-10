import numpy as np
import pandas as pd
import yaml

from strategy import PLUGIN, _fit


class _Context:
    def __init__(self, signal_date, frame, history):
        self.signal_date = signal_date
        self.frame = frame.copy()
        self._history = history

    def history(self, security_id, sessions=430):
        return self._history(security_id, self.signal_date, sessions)


def _config():
    return yaml.safe_load("\n".join([
        "market: {beta_min: 2.0, adv20_min: 50000000, preferred_beta: 2.5, preferred_adv20: 100000000}",
        "channel: {weekly_windows: [12, 16, 20, 26], monthly_windows: [9, 12, 15, 18], width_min_log: 0.12, width_max_log: 1.0, min_full_swings: 1.0, min_clarity: 55.0, min_drift_126: -0.15, max_drift_126: 0.25, min_inside: 0.70, max_parallel_error: 0.60, touch_fraction: 0.18, min_touches_each: 2, max_position: 0.55, preferred_position: 0.35, max_breakdown_fraction: 0.08}",
        "readiness: {minimum_confirmations: 1, max_one_day_rise: 0.08, max_five_day_rise: 0.15, severe_five_day_drop: -0.12, severe_three_day_red_body_mean: 0.04}",
        "selection: {max_candidates: 10}",
    ]))


def _bars(end="2024-10-01"):
    days = pd.bdate_range(end=end, periods=390)
    phase = np.linspace(0, 6 * np.pi, len(days))
    level = 100 + 13 * np.sin(phase)
    bars = pd.DataFrame({"date": days, "open": level, "high": level + 2,
                         "low": level - 2, "close": level,
                         "volume": np.full(len(days), 1_000_000)})
    bars.attrs["backend"] = "research_infrastructure_v1"
    return bars


def test_market_gate_and_future_mutation():
    day = pd.Timestamp("2024-10-01")
    bars = _bars()
    calls = []

    def history(security_id, cutoff, sessions):
        calls.append((security_id, cutoff, sessions))
        result = bars.loc[bars.date <= cutoff].copy()
        result.attrs["backend"] = "research_infrastructure_v1"
        return result

    frame = pd.DataFrame({"symbol": ["AAA", "BBB"], "security_name": ["AAA", "BBB"],
                          "security_id": ["id-a", "id-b"], "close": [100., 100.],
                          "market_input_safe": [True, True],
                          "beta_spy_126": [2.2, 1.9],
                          "avg_dollar_volume_20": [60_000_000., 60_000_000.]})
    config = _config()
    context = _Context(day, frame, history)
    before = PLUGIN.candidate_diagnostics(context, config)
    assert before.loc[1, "reason"] == "market_below_gate"
    assert len(calls) == 1
    assert calls[0] == ("id-a", day, 430)
    future = bars.iloc[-1:].copy()
    future["date"] = day + pd.Timedelta(days=1)
    future["close"] = 1000000.
    bars = pd.concat([bars, future], ignore_index=True)
    bars.attrs["backend"] = "research_infrastructure_v1"
    after = PLUGIN.candidate_diagnostics(_Context(day, frame, history), config)
    pd.testing.assert_frame_equal(before, after)


def test_channel_is_past_only_and_selection_is_bounded():
    config = _config()
    bars = _bars().tail(126).reset_index(drop=True)
    weekly = (bars.set_index("date").resample("W-FRI")
              .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
              .dropna().reset_index())
    result = _fit(weekly.tail(20), "weekly", config["channel"])
    assert isinstance(result["eligible"], bool)
    candidates = pd.DataFrame({"symbol": [f"S{i:02}" for i in range(12)],
                               "strategy_score": range(12)})
    selected = PLUGIN.select(candidates, config)
    assert len(selected) == 10
    assert selected.iloc[0].symbol == "S11"

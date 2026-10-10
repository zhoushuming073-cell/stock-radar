"""Q2 v1.3: causal historical channel selection; no data access in this plugin."""
from __future__ import annotations

import math
from typing import Any, Mapping

import numpy as np
import pandas as pd

from radar.strategy.base import StrategyPlugin
from radar.strategy.context import StrategyContext


def _pivots(values: np.ndarray, low: bool) -> list[int]:
    found = []
    for index in range(2, len(values) - 2):
        span = values[index - 2:index + 3]
        if low:
            match = values[index] == span.min() and np.sum(span == values[index]) == 1
            prominent = min(span[:2].max(), span[3:].max()) - values[index] >= .025
        else:
            match = values[index] == span.max() and np.sum(span == values[index]) == 1
            prominent = values[index] - max(span[:2].min(), span[3:].min()) >= .025
        if match and prominent and (not found or index - found[-1] >= 3):
            found.append(index)
    return found


def _slope(values: np.ndarray) -> float:
    i, j = np.triu_indices(len(values), k=3)
    return float(np.median((values[j] - values[i]) / (j - i))) if len(i) else 0.0


def _aggregate(bars: pd.DataFrame, frequency: str) -> pd.DataFrame:
    return (bars.set_index("date").resample(frequency, label="right", closed="right")
            .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
            .dropna(subset=["close"]).reset_index())


def _fit(bucket: pd.DataFrame, timeframe: str, cfg: Mapping[str, Any]) -> dict[str, Any]:
    n = len(bucket)
    high, low, close = [np.log(bucket[name].to_numpy(dtype=float))
                        for name in ("high", "low", "close")]
    time = np.arange(n)
    slope = _slope((high + low + close) / 3)
    floor = float(np.quantile(low - slope * time, .14))
    ceiling = float(np.quantile(high - slope * time, .86))
    width = ceiling - floor
    if not cfg["width_min_log"] <= width <= cfg["width_max_log"]:
        return {"eligible": False, "reason": "width"}
    floor_at = floor + slope * time
    ceiling_at = ceiling + slope * time
    position = float((close[-1] - floor_at[-1]) / width)
    low_distance = np.abs((low - floor_at) / width)
    high_distance = np.abs((high - ceiling_at) / width)
    low_pivots = [i for i in _pivots(low, True) if low_distance[i] <= cfg["touch_fraction"]]
    high_pivots = [i for i in _pivots(high, False) if high_distance[i] <= cfg["touch_fraction"]]
    events = sorted([(i, "L") for i in low_pivots] + [(i, "H") for i in high_pivots])
    alternating = []
    for event in events:
        if alternating and (event[1] == alternating[-1][1] or event[0] - alternating[-1][0] < 2):
            continue
        alternating.append(event)
    swings = max(0, len(alternating) - 1) / 2
    parallel_error = float(abs(_slope(high) - _slope(low)) * (n - 1) / width)
    inside = float((((close - floor_at) / width >= -.10) &
                    ((close - floor_at) / width <= 1.10)).mean())
    span = max(1, (bucket.date.iloc[-1] - bucket.date.iloc[0]).days * 5 / 7)
    normalized_log_drift = float(slope * (n - 1) * 126 / span)
    normalized_drift = math.expm1(normalized_log_drift)
    retests = .5 * min(1, len(low_pivots) / 3) + .5 * min(1, len(high_pivots) / 3)
    parallel = max(0, 1 - parallel_error / cfg["max_parallel_error"])
    drift_quality = max(0, 1 - abs(normalized_log_drift) / math.log1p(cfg["max_drift_126"]))
    clarity = 100 * (.25 * retests + .25 * min(1, swings / 2) +
                     .20 * parallel + .15 * inside + .15 * drift_quality)
    tests = {
        "contacts": min(len(low_pivots), len(high_pivots)) >= cfg["min_touches_each"],
        "swings": swings >= cfg["min_full_swings"],
        "parallel": parallel_error <= cfg["max_parallel_error"],
        "coverage": inside >= cfg["min_inside"],
        "drift": cfg["min_drift_126"] <= normalized_drift <= cfg["max_drift_126"],
        "clarity": clarity >= cfg["min_clarity"],
        "breakout": position < 1.12,
    }
    return {"eligible": all(tests.values()), "tests": tests, "timeframe": timeframe,
            "window": n, "clarity": clarity, "position": position,
            "lower": math.exp(floor_at[-1]), "upper": math.exp(ceiling_at[-1]),
            "swings": swings, "parallel_error": parallel_error,
            "normalized_drift": normalized_drift}


def _readiness(bars: pd.DataFrame, fit: Mapping[str, Any], cfg: Mapping[str, Any]) -> dict[str, Any]:
    x = bars.tail(30)
    close, low, high, opened = [x[name].to_numpy(dtype=float)
                                for name in ("close", "low", "high", "open")]
    position = math.log(close[-1] / fit["lower"]) / math.log(fit["upper"] / fit["lower"])
    higher_low = low[-3:].min() >= low[-8:-3].min() * .995
    rising = close[-1] > close[-2] > close[-3]
    locations = (close[-3:] - low[-3:]) / np.maximum(high[-3:] - low[-3:], 1e-12)
    improving_location = float(locations.mean()) >= .55
    above_ma5 = close[-1] >= close[-5:].mean()
    count = sum((higher_low, rising, improving_location, above_ma5))
    one_day = close[-1] / close[-2] - 1
    five_day = close[-1] / close[-6] - 1
    red = np.maximum(opened - close, 0) / close
    severe = (five_day < cfg["severe_five_day_drop"] and
              close[-1] < close[-2] < close[-3] and
              float(red[-3:].mean()) >= cfg["severe_three_day_red_body_mean"])
    breakdown = (position < -fit.get("max_breakdown_fraction", .08) or
                 np.all(close[-2:] < fit["lower"] *
                        math.exp(-.03 * math.log(fit["upper"] / fit["lower"]))))
    extended = one_day > cfg["max_one_day_rise"] or five_day > cfg["max_five_day_rise"]
    return {"position": position, "confirmations": count, "severe": bool(severe),
            "breakdown": bool(breakdown), "extended": bool(extended)}


class Q2RelaxedChannel(StrategyPlugin):
    def __init__(self) -> None:
        self._last_context = None
        self._last_config = None
        self._last_result = None

    def required_features(self) -> set[str]:
        return {"beta_spy_126", "avg_dollar_volume_20", "market_input_safe"}

    def _analysis(self, context: StrategyContext, config: Mapping[str, Any]) -> pd.DataFrame:
        if self._last_context is context and self._last_config is config:
            return self._last_result.copy(deep=True)
        market, channel, ready = config["market"], config["channel"], config["readiness"]
        output = []
        for row in context.frame.itertuples(index=False):
            state = {"market": False, "structure": False, "low_region": False,
                     "readiness": False, "selected": False, "score": 0.0,
                     "reason": "market_input_unsafe"}
            if not row.market_input_safe or not np.isfinite(row.beta_spy_126) or not np.isfinite(row.avg_dollar_volume_20):
                output.append(state)
                continue
            if row.beta_spy_126 < market["beta_min"] or row.avg_dollar_volume_20 < market["adv20_min"]:
                state["reason"] = "market_below_gate"
                output.append(state)
                continue
            state["market"] = True
            try:
                bars = context.history(row.security_id, 430)
                if bars.attrs.get("backend") != "research_infrastructure_v1":
                    raise ValueError("unverified history backend")
                bars = bars.loc[pd.to_datetime(bars.date) <= context.signal_date].copy()
                if len(bars) < 205 or pd.Timestamp(bars.date.iloc[-1]) != context.signal_date:
                    raise ValueError("insufficient channel history")
                if not np.isfinite(bars[["open", "high", "low", "close", "volume"]].to_numpy(dtype=float)).all():
                    raise ValueError("unsafe channel bar")
                weeks = _aggregate(bars, "W-FRI")
                months = _aggregate(bars, "ME")
                fits = []
                for name, series, windows in (("weekly", weeks, channel["weekly_windows"]),
                                              ("monthly", months, channel["monthly_windows"])):
                    for length in windows:
                        if len(series) >= length:
                            fits.append(_fit(series.tail(length).reset_index(drop=True), name, channel))
                valid = [fit for fit in fits if fit["eligible"]]
                if not valid:
                    state["reason"] = "no_clear_channel"
                    output.append(state)
                    continue
                fit = max(valid, key=lambda value: (value["clarity"], value["window"], value["timeframe"]))
                fit["max_breakdown_fraction"] = channel["max_breakdown_fraction"]
                state["structure"] = True
                current = _readiness(bars, fit, ready)
                position = current["position"]
                if position > channel["max_position"]:
                    state["reason"] = "above_low_region"
                    output.append(state)
                    continue
                state["low_region"] = True
                if (current["breakdown"] or current["severe"] or current["extended"] or
                        current["confirmations"] < ready["minimum_confirmations"]):
                    state["reason"] = ("breakdown" if current["breakdown"] else
                                       "severe_downside" if current["severe"] else
                                       "extended_wait" if current["extended"] else "readiness_missing")
                    output.append(state)
                    continue
                state["readiness"] = state["selected"] = True
                position_score = max(0.0, 1 - max(0.0, position) / channel["max_position"])
                preferred = (row.beta_spy_126 >= market["preferred_beta"] and
                             row.avg_dollar_volume_20 >= market["preferred_adv20"])
                state["score"] = (.50 * fit["clarity"] + 25 * current["confirmations"] / 4 +
                                  15 * position_score + 10 * preferred)
                state["reason"] = "selected"
            except (ValueError, KeyError, TypeError, ZeroDivisionError) as error:
                state["reason"] = f"history_excluded:{type(error).__name__}"
            output.append(state)
        result = pd.DataFrame(output, index=context.frame.index)
        self._last_context, self._last_config, self._last_result = context, config, result
        return result.copy(deep=True)

    def hard_filter(self, context: StrategyContext, config: Mapping[str, Any]) -> pd.Series:
        return self._analysis(context, config)["selected"].astype(bool)

    def score(self, context: StrategyContext, config: Mapping[str, Any]) -> pd.Series:
        return self._analysis(context, config)["score"].astype(float)

    def select(self, candidates: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
        maximum = min(10, int(config["selection"]["max_candidates"]))
        return candidates.sort_values(["strategy_score", "symbol"],
                                      ascending=[False, True], kind="stable").head(maximum).copy()

    def candidate_diagnostics(self, context: StrategyContext, config: Mapping[str, Any]) -> pd.DataFrame:
        return self._analysis(context, config)


PLUGIN = Q2RelaxedChannel()

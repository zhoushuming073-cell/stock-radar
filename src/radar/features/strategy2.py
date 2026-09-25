"""Causal inputs for strategy 2: recognizing a pullback inside an uptrend.

Every statistic below is built from today's close and earlier sessions only.
Rolling windows carry ``min_periods`` equal to their length, so a partially warmed
value is never emitted. Divisions with a zero denominator return NaN rather than
infinity, and missing sessions are never filled: a gap stays missing instead of
borrowing a neighbouring price. Apart from the two reclaim flags everything is a
continuous variable, so downstream thresholds can be tuned later.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .base import _safe_divide, _true_range

MA_WINDOWS = (20, 50)
SLOPE_WINDOW = 5
RELATIVE_STRENGTH_WINDOW = 20
PULLBACK_WINDOW = 20
RED_DAY_WINDOWS = (5, 10)
LOSS_WINDOW = 10
ATR_WINDOW = 20
DRAWDOWN_WINDOW = 20
RANGE_FAST_WINDOW = 3
RANGE_SLOW_WINDOW = 10
NEW_LOW_WINDOW = 10
SUPPORT_WINDOW = 20
RECLAIM_WINDOWS = (5, 10)

PRICE_COLUMNS = ("high", "low", "close")

FEATURE_COLUMNS = (
    "ma20_slope_5",
    "ma50_slope_5",
    "relative_strength_spy_20",
    "relative_strength_qqq_20",
    "pullback_days_20",
    "red_day_count_5",
    "red_day_count_10",
    "max_single_day_loss_10",
    "atr_normalized_drawdown_20",
    "range_3_over_10",
    "new_low_frequency_10",
    "reclaim_ma_5",
    "reclaim_ma_10",
)


def compute_strategy2_features(
    bars: pd.DataFrame,
    spy_close: pd.Series,
    qqq_close: pd.Series,
) -> pd.DataFrame:
    """Return the strategy-2 feature block on the bar dates of ``bars``.

    ``bars`` holds one symbol's sessions indexed by ascending date with columns
    high, low and close; ``spy_close`` and ``qqq_close`` are the benchmark closes
    on the same date convention. Benchmark values outside the bar calendar are
    ignored and never forward filled, so relative strength is NaN whenever either
    leg cannot be measured over the full window.

    ``max_single_day_loss_10`` and ``atr_normalized_drawdown_20`` are negative for
    a losing/extended name; ``pullback_days_20`` counts trading sessions since the
    most recent 20-session high (zero on the peak day itself).
    """
    missing = [column for column in PRICE_COLUMNS if column not in bars.columns]
    if missing:
        raise ValueError(f"bars is missing columns: {', '.join(missing)}")
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError("bars must have unique, ascending session dates")

    prices = bars[list(PRICE_COLUMNS)].astype(float)
    high, low, close = (prices[column] for column in PRICE_COLUMNS)
    daily_return = close.pct_change(fill_method=None)
    result = pd.DataFrame(index=bars.index)

    for window in MA_WINDOWS:
        moving_average = close.rolling(window, min_periods=window).mean()
        earlier = moving_average.shift(SLOPE_WINDOW)
        result[f"ma{window}_slope_{SLOPE_WINDOW}"] = _safe_divide(moving_average - earlier, earlier)

    stock_return = close.pct_change(RELATIVE_STRENGTH_WINDOW, fill_method=None)
    for name, benchmark in (("spy", spy_close), ("qqq", qqq_close)):
        aligned = benchmark.reindex(bars.index).astype(float)
        benchmark_return = aligned.pct_change(RELATIVE_STRENGTH_WINDOW, fill_method=None)
        result[f"relative_strength_{name}_{RELATIVE_STRENGTH_WINDOW}"] = (
            stock_return - benchmark_return
        )

    # Distance to the most recent maximum within the completed 20-session
    # window. Sliding NumPy windows avoid a slow per-row Python callback.
    days_since_peak = np.full(len(bars), np.nan)
    if len(bars) >= PULLBACK_WINDOW:
        windows = np.lib.stride_tricks.sliding_window_view(high.to_numpy(), PULLBACK_WINDOW)
        valid = np.isfinite(windows).all(axis=1)
        distance = np.argmax(windows[:, ::-1], axis=1).astype(float)
        days_since_peak[PULLBACK_WINDOW - 1:] = np.where(valid, distance, np.nan)
    result[f"pullback_days_{PULLBACK_WINDOW}"] = days_since_peak

    is_red = daily_return.lt(0).where(daily_return.notna())
    for window in RED_DAY_WINDOWS:
        result[f"red_day_count_{window}"] = is_red.rolling(window, min_periods=window).sum()

    result[f"max_single_day_loss_{LOSS_WINDOW}"] = (
        daily_return.rolling(LOSS_WINDOW, min_periods=LOSS_WINDOW).min().clip(upper=0.0)
    )

    true_range = _true_range(high, low, close)
    atr = true_range.rolling(ATR_WINDOW, min_periods=ATR_WINDOW).mean()
    result[f"atr_normalized_drawdown_{DRAWDOWN_WINDOW}"] = _safe_divide(
        close - high.rolling(DRAWDOWN_WINDOW, min_periods=DRAWDOWN_WINDOW).max(), atr
    )

    bar_range_pct = _safe_divide(high - low, close)
    result[f"range_{RANGE_FAST_WINDOW}_over_{RANGE_SLOW_WINDOW}"] = _safe_divide(
        bar_range_pct.rolling(RANGE_FAST_WINDOW, min_periods=RANGE_FAST_WINDOW).mean(),
        bar_range_pct.rolling(RANGE_SLOW_WINDOW, min_periods=RANGE_SLOW_WINDOW).mean(),
    )

    # Support is the lowest low of the 20 sessions ending yesterday, so today's
    # break is judged against a level already known before the open.
    support = low.rolling(SUPPORT_WINDOW, min_periods=SUPPORT_WINDOW).min().shift(1)
    broke_support = low.lt(support).astype(float).where(support.notna())
    result[f"new_low_frequency_{NEW_LOW_WINDOW}"] = (
        broke_support.rolling(NEW_LOW_WINDOW, min_periods=NEW_LOW_WINDOW).mean()
    )

    for window in RECLAIM_WINDOWS:
        moving_average = close.rolling(window, min_periods=window).mean()
        below_before = close.shift(1).le(moving_average.shift(1))
        result[f"reclaim_ma_{window}"] = (
            (close.gt(moving_average) & below_before)
            .astype("boolean")
            .where(moving_average.notna() & moving_average.shift(1).notna())
        )

    return result[list(FEATURE_COLUMNS)]

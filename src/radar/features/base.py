"""Causal per-symbol base features built from OHLCV bars.

Every rolling window requires a full window of observations (``min_periods``
equals the window), so no partially warmed value is ever emitted. Divisions with
a zero denominator yield NaN instead of infinity, and nothing is forward filled:
a missing session stays missing rather than borrowing a later price.

The column set matches ``RESEARCH_COLUMNS['daily_features']`` for the base block
only; beta, idiosyncratic volatility and elasticity are computed elsewhere.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

RETURN_WINDOWS = (1, 3, 5, 20, 40, 60)
MA_WINDOWS = (5, 10, 20, 50)
ATR_WINDOWS = (14, 20)
EXTREME_WINDOWS = (20, 60)
VOLATILITY_WINDOWS = (20, 60)
VOLUME_WINDOW = 20
SUPPORT_WINDOW = 20
EVENT_WINDOW = 5
CONTRACTION_FAST_WINDOW = 5
TRADING_DAYS = 252

OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


def _safe_divide(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    """Divide while turning a zero (or non-finite) denominator into NaN."""
    usable = denominator.where(denominator.notna() & (denominator != 0) & np.isfinite(denominator))
    return numerator / usable


def _true_range(high: pd.Series, low: pd.Series, close: pd.Series) -> pd.Series:
    """Wilder's true range: the largest of today's span and the gaps to the prior close."""
    previous_close = close.shift(1)
    span = high - low
    upper_gap = (high - previous_close).abs()
    lower_gap = (low - previous_close).abs()
    result = pd.concat([span, upper_gap, lower_gap], axis=1).max(axis=1)
    return result.where(previous_close.notna() | (np.arange(len(close)) == 0))


def compute_base_features(frame: pd.DataFrame) -> pd.DataFrame:
    """Return base features on the bar dates of ``frame``.

    ``frame`` holds one symbol's bars indexed by ascending session date with
    columns open, high, low, close and volume. Returns use ``pct_change`` with no
    filling, so a gap between sessions produces NaN rather than a synthetic
    one-session move.
    """
    missing = [column for column in OHLCV_COLUMNS if column not in frame.columns]
    if missing:
        raise ValueError(f"frame is missing columns: {', '.join(missing)}")
    if frame.index.has_duplicates or not frame.index.is_monotonic_increasing:
        raise ValueError("frame must have unique, ascending session dates")

    bars = frame[list(OHLCV_COLUMNS)].astype(float)
    open_, high, low, close, volume = (bars[column] for column in OHLCV_COLUMNS)
    result = pd.DataFrame(index=frame.index)

    for window in RETURN_WINDOWS:
        result[f"ret_{window}"] = close.pct_change(window, fill_method=None)

    daily_return = close.pct_change(fill_method=None)
    for window in VOLATILITY_WINDOWS:
        result[f"realized_vol_{window}"] = (
            daily_return.rolling(window, min_periods=window).std(ddof=1) * np.sqrt(TRADING_DAYS)
        )

    for window in MA_WINDOWS:
        moving_average = close.rolling(window, min_periods=window).mean()
        result[f"ma_{window}"] = moving_average
        result[f"dist_ma_{window}"] = _safe_divide(close - moving_average, moving_average)

    true_range = _true_range(high, low, close)
    atr = {}
    for window in ATR_WINDOWS:
        atr[window] = true_range.rolling(window, min_periods=window).mean()
        result[f"atr_{window}"] = atr[window]
        result[f"atr_pct_{window}"] = _safe_divide(atr[window], close)
    result["atr_contraction"] = _safe_divide(atr[ATR_WINDOWS[0]], atr[ATR_WINDOWS[1]])

    dollar_volume = close * volume
    result["avg_volume_20"] = volume.rolling(VOLUME_WINDOW, min_periods=VOLUME_WINDOW).mean()
    result["avg_dollar_volume_20"] = dollar_volume.rolling(
        VOLUME_WINDOW, min_periods=VOLUME_WINDOW
    ).mean()

    for window in EXTREME_WINDOWS:
        rolling_high = high.rolling(window, min_periods=window).max()
        rolling_low = low.rolling(window, min_periods=window).min()
        result[f"high_{window}"] = rolling_high
        result[f"low_{window}"] = rolling_low
        result[f"drawdown_{window}"] = _safe_divide(close - rolling_high, rolling_high)

    for window in (EVENT_WINDOW, 10):
        window_low = low.rolling(window, min_periods=window).min()
        result[f"rebound_from_low_{window}"] = _safe_divide(close - window_low, window_low)

    bar_range = high - low
    body_high = pd.concat([open_, close], axis=1).max(axis=1)
    body_low = pd.concat([open_, close], axis=1).min(axis=1)
    upper_wick = high - body_high
    lower_wick = body_low - low
    result["body_pct"] = _safe_divide(close - open_, open_)
    result["upper_wick_ratio"] = _safe_divide(upper_wick, bar_range)
    result["lower_wick_ratio"] = _safe_divide(lower_wick, bar_range)
    result["close_location"] = _safe_divide(close - low, bar_range)
    result["range_pct"] = _safe_divide(bar_range, close)

    red_body = (-result["body_pct"]).clip(lower=0.0)
    for window in (3, 5):
        result[f"red_body_avg_{window}"] = red_body.rolling(window, min_periods=window).mean()

    result["decline_speed_3"] = close.pct_change(3, fill_method=None)
    result["decline_speed_prev_3"] = result["decline_speed_3"].shift(3)
    result["decline_acceleration"] = result["decline_speed_3"] - result["decline_speed_prev_3"]

    result["range_contraction"] = _safe_divide(
        result["range_pct"].rolling(CONTRACTION_FAST_WINDOW, min_periods=CONTRACTION_FAST_WINDOW).mean(),
        result["range_pct"].rolling(VOLUME_WINDOW, min_periods=VOLUME_WINDOW).mean(),
    )
    result["volume_contraction"] = _safe_divide(
        volume.rolling(CONTRACTION_FAST_WINDOW, min_periods=CONTRACTION_FAST_WINDOW).mean(),
        volume.rolling(VOLUME_WINDOW, min_periods=VOLUME_WINDOW).mean(),
    )

    is_down_day = (daily_return < 0).where(daily_return.notna())
    down_volume = volume.where(is_down_day.eq(True), 0.0).where(is_down_day.notna())
    result["down_volume_ratio"] = _safe_divide(
        down_volume.rolling(VOLUME_WINDOW, min_periods=VOLUME_WINDOW).sum(),
        volume.rolling(VOLUME_WINDOW, min_periods=VOLUME_WINDOW).sum(),
    )

    # Support is the lowest low of the 20 sessions ending yesterday, so every
    # comparison below uses a level that was already known at today's open.
    support = low.rolling(SUPPORT_WINDOW, min_periods=SUPPORT_WINDOW).min().shift(1)
    broke_support = (low < support).astype("float").where(support.notna())
    result["new_low_frequency_5"] = (
        broke_support.rolling(EVENT_WINDOW, min_periods=EVENT_WINDOW).sum() / EVENT_WINDOW
    )

    failed_breakdown = ((low < support) & (close >= support)).astype("boolean").where(support.notna())
    support_reclaim = ((close > support) & (close.shift(1) <= support.shift(1))).astype("boolean").where(
        support.notna() & support.shift(1).notna()
    )
    higher_low_proxy = ((low > low.shift(1)) & (low.shift(1) < low.shift(2))).astype("boolean")
    result["failed_breakdown"] = failed_breakdown
    result["support_reclaim"] = support_reclaim
    result["higher_low_proxy"] = higher_low_proxy

    return result

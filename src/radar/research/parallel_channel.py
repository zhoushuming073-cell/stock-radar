"""Past-only multi-timeframe parallel channel discovery (research-only v1).

No market-data access, outcome labels, orders, Strategy 2, or frozen data writes.
Input is split-adjusted DAILY OHLCV through a declared decision session.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd

VERSION = "parallel-channel-v1"
COLUMNS = ("date", "open", "high", "low", "close", "volume")


@dataclass(frozen=True)
class ChannelSettings:
    weekly_windows: tuple[int, ...] = (12, 16, 20, 26)
    monthly_windows: tuple[int, ...] = (9, 12, 15, 18)
    min_daily_bars: int = 205
    min_weekly_bars: int = 26
    min_monthly_bars: int = 9
    min_dollar_volume_20: float = 1_000_000.0
    min_price: float = 2.0
    width_min_log: float = 0.10
    width_max_log: float = 0.85
    max_negative_drift: float = 0.20
    max_positive_drift: float = 0.30
    max_parallel_error: float = 0.60
    touch_fraction: float = 0.18
    min_weekly_touches: int = 2
    min_monthly_touches: int = 2
    min_alternations: int = 2
    min_inside_fraction: float = 0.70
    min_channel_quality: float = 58.0
    max_entry_position: float = 0.42
    max_breach_fraction: float = 0.12


def _ramp(x: float, lo: float, hi: float) -> float:
    if hi <= lo:
        raise ValueError("bad ramp")
    return float(np.clip((x - lo) / (hi - lo), 0, 1))


def _validate(frame: pd.DataFrame, asof: str | pd.Timestamp, cfg: ChannelSettings) -> pd.DataFrame:
    if not set(COLUMNS).issubset(frame.columns):
        raise ValueError(f"missing columns: {sorted(set(COLUMNS) - set(frame))}")
    if not len(frame):
        raise ValueError("empty daily bars")
    x = frame.loc[:, COLUMNS].copy()
    x["date"] = pd.to_datetime(x["date"], errors="raise")
    if x.date.isna().any() or x.date.dt.tz is not None:
        raise ValueError("dates must be timezone-naive market sessions")
    if x.date.duplicated().any() or not x.date.is_monotonic_increasing:
        raise ValueError("unsorted or duplicate dates")
    for k in COLUMNS[1:]:
        x[k] = pd.to_numeric(x[k], errors="raise")
    asof = pd.Timestamp(asof)
    if asof.tzinfo is not None:
        raise ValueError("asof must be a market-session date")
    x = x.loc[x.date <= asof].reset_index(drop=True)
    if len(x) < cfg.min_daily_bars or x.date.iloc[-1] != asof:
        raise ValueError("inadequate history or missing decision session")
    a = x[list(COLUMNS[1:])].to_numpy(dtype=float)
    if not np.isfinite(a).all() or (a[:, :4] <= 0).any() or (a[:, 4] < 0).any():
        raise ValueError("non-finite or non-positive prices/negative volume")
    if (a[:, 1] < a[:, [0, 2, 3]].max(axis=1)).any() or (a[:, 2] > a[:, [0, 3]].min(axis=1)).any():
        raise ValueError("invalid OHLC")
    # Long trading gaps are usually missing candles / halts, not a normal weekly pattern.
    if x.date.diff().dt.days.iloc[-cfg.min_daily_bars + 1:].gt(12).any():
        raise ValueError("large missing-session gap")
    return x


def _aggregate(x: pd.DataFrame, freq: str) -> pd.DataFrame:
    r = (x.set_index("date").resample(freq, label="right", closed="right")
         .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"})
         .dropna(subset=["close"]).reset_index())
    # The last bucket is partial if asof is not the end of that week/month.
    return r


def _slope(y: np.ndarray) -> float:
    # Median pairwise slope, using only observed prefix; robust to isolated wicks.
    n = len(y)
    return float(np.median([(y[j] - y[i]) / (j - i)
                            for i in range(n) for j in range(i + 3, n)]))


def _pivots(y: np.ndarray, side: str) -> list[int]:
    # A pivot needs observations on BOTH sides, so the final bar is never a pivot.
    xs = []
    for i in range(2, len(y) - 2):
        q = y[i - 2:i + 3]
        if side == "low" and y[i] <= q.min() and np.sum(q == y[i]) == 1:
            xs.append(i)
        if side == "high" and y[i] >= q.max() and np.sum(q == y[i]) == 1:
            xs.append(i)
    return xs


def _distinct(xs: list[int], distance: int = 3) -> list[int]:
    out = []
    for i in xs:
        if not out or i - out[-1] >= distance:
            out.append(i)
    return out


def _fit(x: pd.DataFrame, tf: str, cfg: ChannelSettings) -> dict[str, Any]:
    n = len(x)
    h = np.log(x.high.to_numpy(dtype=float))
    l = np.log(x.low.to_numpy(dtype=float))
    c = np.log(x.close.to_numpy(dtype=float))
    t = np.arange(n)
    # Both boundaries share the median-price trend. Separate high/low slopes
    # diagnose widening/funneling instead of silently forcing all data parallel.
    s = _slope((h + l + c) / 3)
    low = float(np.quantile(l - s * t, 0.14))
    high = float(np.quantile(h - s * t, 0.86))
    width = high - low
    if width <= 0:
        return {"timeframe": tf, "eligible": False, "reason": "degenerate_width", "quality": 0.0}
    ld = (l - (low + s * t)) / width
    hd = ((high + s * t) - h) / width
    cd = (c - (low + s * t)) / width
    # Support / resistance contacts are distinct confirmed local extrema,
    # not five neighboring candles counting as five separate tests.
    low_pivots = _distinct([i for i in _pivots(l, "low") if abs(ld[i]) <= cfg.touch_fraction])
    high_pivots = _distinct([i for i in _pivots(h, "high") if abs(hd[i]) <= cfg.touch_fraction])
    events = sorted([(i, "L") for i in low_pivots] + [(i, "H") for i in high_pivots])
    alternating = []
    for i, side in events:
        if alternating and side == alternating[-1][1]:
            continue
        if alternating and i - alternating[-1][0] < 2:
            continue
        alternating.append((i, side))
    alternations = max(0, len(alternating) - 1)
    slope_low = _slope(l)
    slope_high = _slope(h)
    drift = float(np.expm1(s * (n - 1)))
    parallel_error = float(abs(slope_high - slope_low) * (n - 1) / width)
    inside = float(((cd >= -0.10) & (cd <= 1.10)).mean())
    below = int((cd < -cfg.max_breach_fraction).sum())
    above = int((cd > 1 + cfg.max_breach_fraction).sum())
    upper = float(np.exp(high + s * (n - 1)))
    lower = float(np.exp(low + s * (n - 1)))
    position = float((c[-1] - (low + s * (n - 1))) / width)
    # Channel quality is not a return predictor. Allow low scoring candidates
    # into diagnostics, but gate the selected sample with structural checks.
    flat = 1 - _ramp(abs(drift), 0.05, 0.32)
    parallel = 1 - _ramp(parallel_error, 0.10, cfg.max_parallel_error)
    contacts = min(1.0, len(low_pivots) / 3) * 0.5 + min(1.0, len(high_pivots) / 3) * 0.5
    swings = min(1.0, alternations / 4)
    quality = 100 * (0.18 * flat + 0.18 * parallel + 0.26 * contacts
                     + 0.23 * swings + 0.15 * inside)
    enough = (len(low_pivots) >= (cfg.min_monthly_touches if tf == "monthly" else cfg.min_weekly_touches)
              and len(high_pivots) >= (cfg.min_monthly_touches if tf == "monthly" else cfg.min_weekly_touches))
    tests = {
        "width": cfg.width_min_log <= width <= cfg.width_max_log,
        "drift": -cfg.max_negative_drift <= drift <= cfg.max_positive_drift,
        "parallel": parallel_error <= cfg.max_parallel_error,
        "contacts": enough,
        "alternation": alternations >= cfg.min_alternations,
        "inside": inside >= cfg.min_inside_fraction,
        "no_breakdown": bool(position >= -cfg.max_breach_fraction
                             and not (cd[-2:] < -cfg.max_breach_fraction).all()),
        "no_major_breakout": bool(position < 0.90),
        "quality": quality >= cfg.min_channel_quality,
    }
    return dict(timeframe=tf, eligible=all(tests.values()), quality=round(quality, 2),
                lower=round(lower, 5), upper=round(upper, 5), position=round(position, 3),
                drift=round(drift, 4), parallel_error=round(parallel_error, 3),
                width_pct=round(float(np.expm1(width)), 4),
                support_touches=len(low_pivots), resistance_touches=len(high_pivots),
                alternations=alternations, coverage=round(inside, 3),
                lower_breaches=below, upper_breaches=above, tests=tests,
                window=n, completed_pivot_lows=low_pivots,
                completed_pivot_highs=high_pivots)


def _daily(x: pd.DataFrame, lower: float, upper: float, cfg: ChannelSettings) -> dict[str, Any]:
    a = x.tail(20).reset_index(drop=True)
    lo = a.low.to_numpy(dtype=float)
    hi = a.high.to_numpy(dtype=float)
    cl = a.close.to_numpy(dtype=float)
    op = a.open.to_numpy(dtype=float)
    last = float(cl[-1])
    width = max(upper - lower, 1e-8)
    position = (last - lower) / width
    best = None
    # A recently completed upward impulse followed by a partial retracement.
    # No use of T+1/T+10 labels; score can be negative for unfinished cycles.
    for i in range(4, 16):
        for j in range(i + 2, 19):
            bounce = hi[j] / lo[i] - 1
            if not (0.04 <= bounce <= 0.40):
                continue
            pullback = (hi[j] - last) / max(hi[j] - lo[i], 1e-8)
            if not (0.15 <= pullback <= 0.85):
                continue
            if min(lo[j + 1:]) < lo[i] * 0.975:
                continue
            v = 25 + 25 * _ramp(bounce, 0.04, 0.16) + 20 * (1 - abs(pullback - 0.45) / 0.45)
            if best is None or v > best[0]:
                best = (v, i, j, bounce, pullback)
    last3 = cl[-3:]
    # Separate price action proxy from claims of institutional buying.
    recent_low = float(lo[-5:].min())
    green = int((cl[-3:] > op[-3:]).sum())
    higher_low = bool(lo[-3:].min() >= lo[-10:-3].min() * 0.99)
    stabilizing = bool((green >= 1 or last3[-1] > last3[0]) and higher_low)
    below_floor = bool(last < lower - cfg.max_breach_fraction * width)
    urgent_down = bool(last < cl[-6] * 0.88 and cl[-1] < cl[-2] < cl[-3])
    close_to_bottom = bool(-cfg.max_breach_fraction <= position <= cfg.max_entry_position)
    cycle_score = float(best[0]) if best is not None else 0.0
    distance_score = 20 * (1 - _ramp(max(0.0, position), 0.0, cfg.max_entry_position))
    entry_score = float(np.clip(cycle_score + distance_score + (15 if stabilizing else 0) -
                                (35 if urgent_down or below_floor else 0), 0, 100))
    stage = ("breakdown" if below_floor or urgent_down else
             "early_reversal" if close_to_bottom and best and stabilizing else
             "near_lower_wait" if close_to_bottom else "not_near_lower")
    return dict(stage=stage, entry_score=round(entry_score, 2),
                channel_position=round(float(position), 3),
                cycle_detected=best is not None,
                impulse_pct=round(float(best[3]), 4) if best else None,
                retracement=round(float(best[4]), 4) if best else None,
                impulse_low_date=str(a.date.iloc[best[1]].date()) if best else None,
                impulse_high_date=str(a.date.iloc[best[2]].date()) if best else None,
                last_five_day_low=round(recent_low, 4), stabilizing=stabilizing,
                higher_low=higher_low, green_last_three=green,
                urgent_down=urgent_down, below_channel=below_floor)


def analyze(frame: pd.DataFrame, asof: str | pd.Timestamp, cfg: ChannelSettings | None = None) -> dict[str, Any]:
    """Analyze one security using only DAILY bars <= asof; never places orders."""
    cfg = cfg or ChannelSettings()
    x = _validate(frame, asof, cfg)
    last = float(x.close.iloc[-1])
    liquid = float((x.close.tail(20) * x.volume.tail(20)).mean())
    base = {"version": VERSION, "asof": str(x.date.iloc[-1].date()),
            "price": round(last, 4), "dollar_volume_20": round(liquid, 2),
            "qualified": False, "watch": False, "reason": None}
    if last < cfg.min_price or liquid < cfg.min_dollar_volume_20:
        return {**base, "reason": "liquidity_or_price", "channels": [], "daily": None}
    weeks = _aggregate(x, "W-FRI")
    months = _aggregate(x, "ME")
    channels = []
    for tf, source, windows, minimum in (
        ("weekly", weeks, cfg.weekly_windows, cfg.min_weekly_bars),
        ("monthly", months, cfg.monthly_windows, cfg.min_monthly_bars),
    ):
        if len(source) < minimum:
            continue
        for n in windows:
            if n <= len(source):
                channels.append(_fit(source.tail(n).reset_index(drop=True), tf, cfg))
    usable = [c for c in channels if c["eligible"]]
    # Prefer the strongest structure, with a small bonus for longer-term evidence.
    usable.sort(key=lambda c: c["quality"] + (3 if c["timeframe"] == "monthly" else 0), reverse=True)
    if not usable:
        return {**base, "reason": "no_valid_channel", "channels": channels, "daily": None}
    best = usable[0]
    daily = _daily(x, best["lower"], best["upper"], cfg)
    watch = daily["stage"] in ("near_lower_wait", "early_reversal")
    combined = round(best["quality"] * 0.75 + daily["entry_score"] * 0.25, 2)
    return {**base, "qualified": True, "watch": watch, "reason": daily["stage"],
            "channel": best, "channels": channels, "daily": daily,
            "rank_score": combined,
            "config": asdict(cfg)}

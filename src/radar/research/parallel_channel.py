"""Past-only multi-timeframe parallel channel discovery (research-only v1).

No market-data access, outcome labels, orders, Strategy 2, or frozen data writes.
Input is split-adjusted DAILY OHLCV through a declared decision session.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import math
from functools import lru_cache

import numpy as np
import pandas as pd

VERSION = "parallel-channel-v1.1"
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
    min_pivot_prominence_log: float = 0.025
    min_consensus_windows: int = 2
    max_band_disagreement: float = 0.35
    max_position_disagreement: float = 0.20
    max_drift_disagreement: float = 0.25


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
    asof = pd.Timestamp(asof)
    from radar.research.sessions import require_session
    require_session(asof)
    x = x.loc[x.date <= asof].reset_index(drop=True)
    if x.date.duplicated().any() or not x.date.is_monotonic_increasing:
        raise ValueError("unsorted or duplicate dates")
    for k in COLUMNS[1:]:
        x[k] = pd.to_numeric(x[k], errors="raise")
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
    z = x.copy()
    z['observed_through'] = z['date']
    r = (z.set_index("date").resample(freq, label="right", closed="right")
         .agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum", 'observed_through': 'max'})
         .dropna(subset=["close"]).reset_index())
    r = r.rename(columns={'date': 'bucket_end'})
    r['date'] = r['observed_through']
    from radar.research.sessions import calendar
    ends = [calendar().date_to_session(d, direction='previous') for d in r.bucket_end]
    r['partial'] = [d < e for d, e in zip(r.date, ends)]
    return r


@lru_cache(maxsize=64)
def _slope_pairs(n):
    i, j = np.triu_indices(n, k=3)
    return i, j


def _slope(y: np.ndarray) -> float:
    # Median pairwise slope, using only observed prefix; robust to isolated wicks.
    n = len(y)
    i, j = _slope_pairs(n)
    return float(np.median((y[j]-y[i])/(j-i)))


def _pivots(y: np.ndarray, side: str, prominence: float = 0.0) -> list[int]:
    # A pivot needs observations on BOTH sides, so the final bar is never a pivot.
    xs = []
    for i in range(2, len(y) - 2):
        q = y[i - 2:i + 3]
        if side == "low" and y[i] <= q.min() and np.sum(q == y[i]) == 1 and min(q[:2].max(), q[3:].max()) - y[i] >= prominence:
            xs.append(i)
        if side == "high" and y[i] >= q.max() and np.sum(q == y[i]) == 1 and y[i] - max(q[:2].min(), q[3:].min()) >= prominence:
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
    low_pivots = _distinct([i for i in _pivots(l, "low", cfg.min_pivot_prominence_log) if abs(ld[i]) <= cfg.touch_fraction])
    high_pivots = _distinct([i for i in _pivots(h, "high", cfg.min_pivot_prominence_log) if abs(hd[i]) <= cfg.touch_fraction])
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
                lower=lower, upper=upper, position=position,
                observed_through=str(x.date.iloc[-1].date()), bucket_end=str(x.bucket_end.iloc[-1].date()),
                partial=bool(x.partial.iloc[-1]), slope=s,
                drift=round(drift, 4), parallel_error=round(parallel_error, 3),
                width_pct=round(float(np.expm1(width)), 4),
                support_touches=len(low_pivots), resistance_touches=len(high_pivots),
                alternations=alternations, coverage=round(inside, 3),
                lower_breaches=below, upper_breaches=above, tests=tests,
                window=n, completed_pivot_lows=low_pivots,
                completed_pivot_highs=high_pivots)


def _daily(x: pd.DataFrame, lower: float, upper: float, cfg: ChannelSettings) -> dict[str, Any]:
    """Confirmed low -> confirmed high -> present pullback, in log coordinates."""
    a = x.tail(30).reset_index(drop=True)
    lo, hi, cl, op = [a[k].to_numpy(dtype=float) for k in ('low','high','close','open')]
    last = float(cl[-1])
    width_log = math.log(upper / lower)
    position = math.log(last / lower) / width_log
    lows = _pivots(np.log(lo), 'low', cfg.min_pivot_prominence_log)
    highs = _pivots(np.log(hi), 'high', cfg.min_pivot_prominence_log)
    best = None
    for i in lows:
        for j in highs:
            if not i + 3 <= j <= len(a)-3 or j < len(a)-15:
                continue
            bounce = hi[j] / lo[i] - 1
            retrace = (hi[j]-last) / (hi[j]-lo[i])
            if not .04 <= bounce <= .40 or not .15 <= retrace <= .85:
                continue
            # Reject noisy zigzags: the impulse must exceed typical daily range.
            typical = float(np.median((hi-lo)/cl))
            if bounce < max(.04, 2.5*typical) or min(lo[j+1:]) < lo[i]*.975:
                continue
            if hi[j] <= np.max(hi[max(0,i-2):i+1]) or lo[i] >= min(lo[j+1:]):
                continue
            value = 25+25*_ramp(bounce,.04,.16)+20*max(0,1-abs(retrace-.45)/.45)
            if best is None or value > best[0]:
                best=(value,i,j,bounce,retrace)
    green = int((cl[-3:]>op[-3:]).sum())
    higher_low = bool(lo[-3:].min() >= lo[-10:-3].min()*.99)
    stabilizing = bool((green>=1 or cl[-1]>cl[-3]) and higher_low)
    below_floor = position < -cfg.max_breach_fraction
    urgent_down = bool(cl[-1]<cl[-6]*.88 and cl[-1]<cl[-2]<cl[-3])
    close_to_bottom = -cfg.max_breach_fraction <= position <= cfg.max_entry_position
    # An undercut is penalized monotonically; it is never a perfect entry distance.
    distance = (1-_ramp(position,0,cfg.max_entry_position)) if position>=0 else max(0,1-abs(position)/cfg.max_breach_fraction)
    score = float(np.clip((best[0] if best else 0)+20*distance+(15 if stabilizing else 0)
                          -(35 if urgent_down or below_floor else 0),0,100))
    stage = ('breakdown' if below_floor or urgent_down else
             'early_reversal' if close_to_bottom and best and stabilizing else
             'near_lower_wait' if close_to_bottom else 'not_near_lower')
    return dict(stage=stage, entry_score=score, channel_position=position,
                position_basis='log(C/L)/log(U/L)', cycle_detected=best is not None,
                impulse_pct=best[3] if best else None, retracement=best[4] if best else None,
                impulse_low_date=str(a.date.iloc[best[1]].date()) if best else None,
                impulse_high_date=str(a.date.iloc[best[2]].date()) if best else None,
                last_five_day_low=float(lo[-5:].min()), stabilizing=stabilizing,
                higher_low=higher_low, green_last_three=green, urgent_down=urgent_down,
                below_channel=below_floor, undercut=position<0, distance_score=20*distance)


def consensus(channels, cfg):
    """All structurally valid fits participate; no lucky best-window selection."""
    valid = [c for c in channels if c.get('eligible')]
    if not valid:
        return {'stable':False,'windows':0,'reason':'no_valid_channel'}
    logs_l=np.log([c['lower'] for c in valid]);logs_u=np.log([c['upper'] for c in valid])
    width=float(np.median(logs_u-logs_l))
    band=float(max(np.ptp(logs_l),np.ptp(logs_u))/width)
    positions=[c['position'] for c in valid]
    pos=float(np.ptp(positions))
    # Convert slopes to the SAME 26-week drift for cross-window comparison.
    drifts=[c['slope']*(26 if c['timeframe']=='weekly' else 6) for c in valid]
    drift=float(np.ptp(drifts))
    stable=(len(valid)>=cfg.min_consensus_windows and band<=cfg.max_band_disagreement
            and pos<=cfg.max_position_disagreement and drift<=cfg.max_drift_disagreement)
    quality=float(np.mean([c['quality'] for c in valid]))
    return dict(stable=bool(stable),windows=len(valid),timeframes=sorted({c['timeframe'] for c in valid}),
                band_disagreement=band,position_disagreement=pos,drift_disagreement=drift,
                lower=float(np.exp(np.median(logs_l))),upper=float(np.exp(np.median(logs_u))),
                quality=quality,reason='stable' if stable else 'insufficient_or_disagreeing_windows')


def analyze(frame: pd.DataFrame, asof: str | pd.Timestamp, cfg: ChannelSettings | None = None,
            *, absolute_tradability=True) -> dict[str, Any]:
    """Causal Q2. Historical scale-free shape input does not certify raw-price liquidity."""
    cfg=cfg or ChannelSettings()
    x=_validate(frame,asof,cfg)
    last=float(x.close.iloc[-1]);liquid=float((x.close.tail(20)*x.volume.tail(20)).mean())
    base=dict(version=VERSION,asof=str(x.date.iloc[-1].date()),price=last,dollar_volume_20=liquid,
              qualified=False,watch=False,reason=None,absolute_tradability_checked=absolute_tradability)
    if absolute_tradability and (last<cfg.min_price or liquid<cfg.min_dollar_volume_20):
        return {**base,'reason':'liquidity_or_price','channels':[],'daily':None,'rank_score':0.0}
    weeks=_aggregate(x,'W-FRI');months=_aggregate(x,'ME')
    channels=[]
    for tf, source, windows, minimum in (
        ('weekly',weeks,cfg.weekly_windows,cfg.min_weekly_bars),
        ('monthly',months,cfg.monthly_windows,cfg.min_monthly_bars)):
        if len(source)>=minimum:
            for n in windows:
                if n<=len(source):channels.append(_fit(source.tail(n).reset_index(drop=True),tf,cfg))
    stability=consensus(channels,cfg)
    if not stability['windows']:
        return {**base,'reason':'no_valid_channel','channels':channels,'daily':None,
                'consensus':stability,'rank_score':0.0}
    daily=_daily(x,stability['lower'],stability['upper'],cfg)
    watch=daily['stage'] in ('near_lower_wait','early_reversal')
    qualified=bool(stability['stable'] and daily['stage']=='early_reversal')
    reason=daily['stage'] if stability['stable'] else stability['reason']
    score=.75*stability['quality']+.25*daily['entry_score']
    return {**base,'qualified':qualified,'watch':bool(watch),'reason':reason,
            'channel':stability,'channels':channels,'daily':daily,'consensus':stability,
            'rank_score':float(score),'config':asdict(cfg)}

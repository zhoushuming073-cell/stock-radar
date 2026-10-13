"""Bounded, causal range recognition independent of labels and trade outcomes.

The detector receives an already trusted, as-of-T OHLCV prefix. A window ending
before T is formed using that window alone; only its subsequent state may read
bars between the window end and T. No future outcome, candidate score or
security-specific exception is an input.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from typing import Protocol

import numpy as np
import pandas as pd

from radar.pit.shape import canonical_hash

VERSION = "box-range-detector-stage-a-v1"
OHLCV = ("open", "high", "low", "close", "volume")
STATES = ("NONE", "DEVELOPING", "CONFIRMED", "BREAKDOWN", "UNCERTAIN")


@dataclass(frozen=True)
class RangeConfig:
    version: str = VERSION
    lookback_sessions: int = 126
    window_lengths: tuple[int, ...] = (42, 63, 84, 105, 126)
    end_stride: int = 5
    max_active_age: int = 20
    min_touch_spacing: int = 5
    pivot_left: int = 3
    pivot_right: int = 3
    min_pivot_prominence_fraction: float = .025
    min_touches_per_side: int = 2
    min_alternations: int = 3
    lower_quantile: float = .12
    upper_quantile: float = .88
    zone_fraction_of_width: float = .10
    min_zone_fraction_of_price: float = .012
    min_width_fraction: float = .08
    max_width_fraction: float = .65
    min_occupancy: float = .65
    max_center_drift: float = .35
    break_closes: int = 2

    def __post_init__(self):
        if self.version != VERSION:
            raise ValueError("unsupported detector version")
        if (self.lookback_sessions != 126 or not self.window_lengths
                or min(self.window_lengths) < 20
                or max(self.window_lengths) > self.lookback_sessions
                or len(self.window_lengths) > 8
                or tuple(sorted(set(self.window_lengths))) != self.window_lengths):
            raise ValueError("invalid bounded window lengths")
        if min(self.end_stride, self.min_touch_spacing, self.pivot_left,
               self.pivot_right, self.max_active_age, self.break_closes) < 1:
            raise ValueError("invalid timing configuration")
        if self.pivot_left != self.pivot_right:
            raise ValueError("SciPy bounded prominence uses symmetric pivot confirmation")
        if not 0 < self.lower_quantile < self.upper_quantile < 1:
            raise ValueError("invalid quantiles")
        if not 0 < self.min_width_fraction < self.max_width_fraction:
            raise ValueError("invalid width limits")
        if not 0 < self.min_occupancy <= 1 or self.max_center_drift <= 0:
            raise ValueError("invalid stability limits")
        if (self.min_touches_per_side < 1 or self.min_alternations < 1
                or self.min_pivot_prominence_fraction < 0
                or self.zone_fraction_of_width <= 0
                or self.min_zone_fraction_of_price <= 0):
            raise ValueError("invalid zone/touch limits")

    @classmethod
    def from_mapping(cls, values: dict) -> "RangeConfig":
        data = dict(values)
        if "window_lengths" in data:
            data["window_lengths"] = tuple(data["window_lengths"])
        if set(data) != set(asdict(cls())):
            raise ValueError("detector config keys must match the versioned contract")
        return cls(**data)

    @property
    def digest(self) -> str:
        return sha256(json.dumps(asdict(self), sort_keys=True,
                                 separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class Touch:
    side: str
    event_date: str
    first_confirmable_at: str
    price: float


@dataclass(frozen=True)
class RangeCandidate:
    formation_start: str
    window_end: str
    first_knowable_at: str
    formation_status: str
    state_at_t: str
    support_zone: tuple[float, float]
    resistance_zone: tuple[float, float]
    support_touches: int
    resistance_touches: int
    completed_alternations: int
    touches: tuple[Touch, ...]
    width_fraction: float
    occupancy: float
    center_drift: float
    zone_stability: float
    current_position: float
    score: float
    false_undercut_recovered: bool
    expired: bool
    rejection_reasons: tuple[str, ...]


@dataclass(frozen=True)
class RangeScan:
    detector: str
    version: str
    config_hash: str
    input_hash: str
    decision_date: str
    security_id: str | None
    source: str | None
    basis: str | None
    ri_semantic_hash: str | None
    evaluated_windows: int
    formation_counts: dict[str, int]
    rejection_counts: dict[str, int]
    candidates: tuple[RangeCandidate, ...]
    structure_exists_in_past: bool
    active_unbroken_box_at_t: bool
    status_at_t: str
    best_historical: RangeCandidate | None
    best_active: RangeCandidate | None


class RangeDetector(Protocol):
    name: str

    def detect(self, history: pd.DataFrame, decision_date: str | pd.Timestamp,
               config: RangeConfig) -> RangeScan: ...


def _validated_prefix(history: pd.DataFrame, decision_date, config: RangeConfig) -> pd.DataFrame:
    if set(history.columns) != {"date", *OHLCV} or history.empty:
        raise ValueError("only date and OHLCV are allowed")
    dates = pd.to_datetime(history.date, errors="raise")
    t = pd.Timestamp(decision_date)
    if t.tzinfo is not None or dates.dt.tz is not None:
        raise ValueError("timezone-aware bars need an explicit market-session conversion")
    if (dates.dt.normalize() != dates).any() or t != t.normalize():
        raise ValueError("daily bars and decision must be session dates")
    if not dates.is_monotonic_increasing or dates.duplicated().any():
        raise ValueError("ordered unique sessions required")
    if dates.iloc[-1] != t or (dates > t).any():
        raise ValueError("input must end exactly at T; post-T bars are forbidden")
    f = history.tail(config.lookback_sessions).copy().reset_index(drop=True)
    if len(f) < min(config.window_lengths):
        raise ValueError("insufficient trusted history for the shortest window")
    f["date"] = pd.to_datetime(f.date)
    values = f[list(OHLCV)].to_numpy(dtype=float)
    if (not np.isfinite(values).all() or (values[:, :4] <= 0).any()
            or (values[:, 4] < 0).any()
            or (f.high < f[["open", "close", "low"]].max(axis=1)).any()
            or (f.low > f[["open", "close"]].min(axis=1)).any()):
        raise ValueError("invalid OHLCV")
    return f


def _independent(events: list[tuple[int, str, float, int]],
                 dates: pd.Series, spacing: int) -> tuple[Touch, ...]:
    kept: list[tuple[int, str, float, int]] = []
    event_counts = Counter(i for i, _, _, _ in events)
    for event in sorted(events, key=lambda x: (x[0], x[1])):
        # An outside bar that simultaneously prints a local high and low is
        # ambiguous, not two independent visits to opposite zones.
        if event_counts[event[0]] > 1:
            continue
        if kept and event[0] - kept[-1][0] < spacing:
            continue
        kept.append(event)
    return tuple(Touch(side, str(dates.iloc[i].date()),
                       str(dates.iloc[confirmed].date()), float(price))
                 for i, side, price, confirmed in kept)


def _quantile_geometry(window: pd.DataFrame, config: RangeConfig):
    low = window.low.to_numpy(dtype=float)
    high = window.high.to_numpy(dtype=float)
    floor = float(np.quantile(low, config.lower_quantile))
    ceiling = float(np.quantile(high, config.upper_quantile))
    tolerance = max((ceiling-floor)*config.zone_fraction_of_width,
                    float(np.median(window.close))*config.min_zone_fraction_of_price)
    events = []
    last = len(window)-1
    for i, (lo, hi) in enumerate(zip(low, high)):
        lower = lo <= floor+tolerance
        upper = hi >= ceiling-tolerance
        if lower != upper:
            events.append((i, "LOWER" if lower else "UPPER",
                           float(lo if lower else hi), last))
    return floor, ceiling, _independent(events, window.date, config.min_touch_spacing)


def _pivot_geometry(window: pd.DataFrame, config: RangeConfig):
    try:
        from scipy.signal import find_peaks
    except ImportError as exc:
        raise RuntimeError("pivot baseline requires the box-detector SciPy extra") from exc
    right = config.pivot_right
    events = []
    for side, values, direction in (
            ("UPPER", window.high.to_numpy(dtype=float), 1),
            ("LOWER", window.low.to_numpy(dtype=float), -1)):
        # SciPy supplies local extrema. Measure their swing only inside the
        # configured left/right confirmation window; full-series prominence or
        # distance filtering could let later peaks revise an earlier signal.
        signed = direction*values
        # Reject plateaus: their endpoint could lie beyond the right-side
        # confirmation window, so a centered plateau date is not causal here.
        indices, _ = find_peaks(signed, plateau_size=(1, 1))
        for i in indices:
            if i < config.pivot_left or i+right >= len(window):
                continue
            prominence = min(signed[i]-np.min(signed[i-config.pivot_left:i]),
                             signed[i]-np.min(signed[i+1:i+right+1]))
            if prominence < config.min_pivot_prominence_fraction*values[i]:
                continue
            events.append((int(i), side, float(values[i]), int(i+right)))
    lows = [e[2] for e in events if e[1] == "LOWER"]
    highs = [e[2] for e in events if e[1] == "UPPER"]
    if not lows or not highs:
        return None
    floor = float(np.median(lows))
    ceiling = float(np.median(highs))
    tolerance = max((ceiling-floor)*config.zone_fraction_of_width,
                    float(np.median(window.close))*config.min_zone_fraction_of_price)
    inliers = [e for e in events if abs(e[2]-(floor if e[1]=="LOWER" else ceiling)) <= tolerance]
    return floor, ceiling, _independent(inliers, window.date, config.min_touch_spacing)


def _candidate(window: pd.DataFrame, through_t: pd.DataFrame, config: RangeConfig,
               geometry) -> tuple[RangeCandidate | None, str]:
    if geometry is None:
        return None, "no_confirmed_pivots"
    floor, ceiling, touches = geometry
    median = float(np.median(window.close))
    width = ceiling-floor
    if width <= 0 or floor <= 0:
        return None, "invalid_geometry"
    width_fraction = width/median
    if not config.min_width_fraction <= width_fraction <= config.max_width_fraction:
        return None, "width"
    tol = max(width*config.zone_fraction_of_width,
              median*config.min_zone_fraction_of_price)
    support = (floor-tol, floor+tol)
    resistance = (ceiling-tol, ceiling+tol)
    if support[1] >= resistance[0]:
        return None, "overlapping_zones"
    closes = window.close.to_numpy(dtype=float)
    occupancy = float(np.mean((closes >= support[0]) & (closes <= resistance[1])))
    third = max(1, len(window)//3)
    center_drift = float(np.median(closes[-third:])/np.median(closes[:third])-1)
    lower = sum(t.side == "LOWER" for t in touches)
    upper = sum(t.side == "UPPER" for t in touches)
    alternations = sum(a.side != b.side for a,b in zip(touches, touches[1:]))
    deviations = [abs(t.price-(floor if t.side=="LOWER" else ceiling))/tol for t in touches]
    stability = float(max(0, 1-np.median(deviations))) if deviations else 0.
    reasons = []
    if lower < config.min_touches_per_side or upper < config.min_touches_per_side:
        reasons.append("insufficient_independent_touches")
    if alternations < config.min_alternations:
        reasons.append("insufficient_alternations")
    if occupancy < config.min_occupancy:
        reasons.append("low_occupancy")
    if abs(center_drift) > config.max_center_drift:
        reasons.append("center_drift")
    if "center_drift" in reasons or alternations < 2:
        return None, "center_drift" if "center_drift" in reasons else "one_sided_or_trend"
    if "low_occupancy" in reasons:
        formation_status = "UNCERTAIN"
    elif reasons:
        formation_status = "DEVELOPING"
    else:
        formation_status = "CONFIRMED"
    t_close = float(through_t.close.iloc[-1])
    position = (t_close-floor)/width
    after = through_t.loc[through_t.date >= window.date.iloc[-1]].close.to_numpy(dtype=float)
    under = after < support[0]
    over = after > resistance[1]
    def persistent(mask):
        return any(bool(mask[i:i+config.break_closes].all())
                   for i in range(len(mask)-config.break_closes+1))
    lower_break = persistent(under)
    upper_break = persistent(over)
    recovered = bool(under.any() and not under[-1] and not lower_break)
    age = len(through_t)-int(through_t.date.searchsorted(window.date.iloc[-1]))-1
    expired = age > config.max_active_age
    if expired:
        state = "NONE"
    elif formation_status != "CONFIRMED":
        state = formation_status
    elif lower_break:
        state = "BREAKDOWN"
    elif upper_break:
        state = "NONE"
    elif under[-1] or over[-1]:
        state = "UNCERTAIN"
    else:
        state = "CONFIRMED"
    score = float(np.clip(.35*occupancy + .25*min(alternations/4, 1)
                          + .20*stability + .20*(1-min(abs(center_drift)/config.max_center_drift, 1)), 0, 1))
    return RangeCandidate(
        str(window.date.iloc[0].date()), str(window.date.iloc[-1].date()),
        str(window.date.iloc[-1].date()), formation_status, state, support,
        resistance, lower, upper, alternations, touches, width_fraction,
        occupancy, center_drift, stability, position, score, recovered, expired,
        tuple(reasons)), ""


class _BaseDetector:
    name = ""

    def geometry(self, window: pd.DataFrame, config: RangeConfig):
        raise NotImplementedError

    def detect(self, history: pd.DataFrame, decision_date,
               config: RangeConfig | None = None) -> RangeScan:
        config = config or RangeConfig()
        f = _validated_prefix(history, decision_date, config)
        dates = f.date
        ends = set(range(min(config.window_lengths)-1, len(f), config.end_stride))
        ends.add(len(f)-1)
        candidates = []
        formation_counts = Counter()
        rejected = Counter()
        evaluated = 0
        for end in sorted(ends):
            for length in config.window_lengths:
                start = end-length+1
                if start < 0:
                    continue
                window = f.iloc[start:end+1].reset_index(drop=True)
                evaluated += 1
                result, reason = _candidate(window, f, config,
                                            self.geometry(window, config))
                if result is None:
                    rejected[reason] += 1
                else:
                    formation_counts[result.formation_status] += 1
                    candidates.append(result)
        confirmed = [c for c in candidates if c.formation_status=="CONFIRMED"]
        active = [c for c in confirmed if c.state_at_t=="CONFIRMED"]
        key = lambda c: (c.score, c.window_end, c.formation_start)
        best_history = max(confirmed, key=key, default=None)
        best_active = max(active, key=key, default=None)
        if best_active:
            status = "CONFIRMED"
        elif any(c.state_at_t=="BREAKDOWN" for c in confirmed):
            status = "BREAKDOWN"
        elif any(c.state_at_t=="UNCERTAIN" for c in candidates):
            status = "UNCERTAIN"
        elif any(c.state_at_t=="DEVELOPING" for c in candidates):
            status = "DEVELOPING"
        else:
            status = "NONE"
        attrs = history.attrs
        return RangeScan(
            self.name, VERSION, config.digest, canonical_hash(f), str(dates.iloc[-1].date()),
            attrs.get("security_id"), attrs.get("source"), attrs.get("basis"),
            attrs.get("semantic_hash"), evaluated, dict(sorted(formation_counts.items())),
            dict(sorted(rejected.items())), tuple(candidates), bool(best_history),
            bool(best_active), status, best_history, best_active)


class QuantileZoneDetector(_BaseDetector):
    name = "quantile-zone-v1"

    def geometry(self, window, config):
        return _quantile_geometry(window, config)


class ConfirmedPivotDetector(_BaseDetector):
    name = "confirmed-pivot-zone-v1"

    def geometry(self, window, config):
        return _pivot_geometry(window, config)

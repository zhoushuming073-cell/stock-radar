"""Causal, research-only lower-band context for a versioned RangeScan.

This module describes the price position at decision close T. It does not
create an order, infer structure truth, or read labels and future returns.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from hashlib import sha256
import json

import numpy as np
import pandas as pd

from radar.pit.shape import canonical_hash
from .range_detector import RangeConfig, RangeScan, _validated_prefix


VERSION = "box-lower-band-context-v1"


@dataclass(frozen=True)
class LowerBandConfig:
    version: str = VERSION
    max_position: float = .33
    min_headroom: float = .08
    max_last_day_gain: float = .06
    max_three_day_gain: float = .10
    min_last_day_return: float = -.005
    min_recent_low_change: float = -.025
    max_volume_ratio: float = 4.0

    def __post_init__(self):
        if self.version != VERSION:
            raise ValueError("unsupported lower-band version")
        if not 0 < self.max_position < 1 or not 0 < self.min_headroom < 1:
            raise ValueError("invalid position or headroom bound")
        if not 0 < self.max_last_day_gain < 1 or not 0 < self.max_three_day_gain < 1:
            raise ValueError("invalid extension bound")
        if not -1 < self.min_last_day_return <= 0 or not -1 < self.min_recent_low_change <= 0:
            raise ValueError("invalid stabilization bound")
        if self.max_volume_ratio <= 1:
            raise ValueError("invalid volume bound")

    @classmethod
    def from_mapping(cls, values: dict) -> "LowerBandConfig":
        if set(values) != set(asdict(cls())):
            raise ValueError("lower-band config keys must match the versioned contract")
        return cls(**values)

    @property
    def digest(self) -> str:
        return sha256(json.dumps(asdict(self), sort_keys=True,
                                 separators=(",", ":")).encode()).hexdigest()


@dataclass(frozen=True)
class LowerBandContext:
    version: str
    config_hash: str
    detector: str
    detector_config_hash: str
    input_hash: str
    decision_date: str
    state: str
    reasons: tuple[str, ...]
    formation_start: str | None
    range_known_at: str | None
    position: float | None
    headroom: float | None
    last_day_return: float | None
    three_day_return: float | None
    recent_low_change: float | None
    volume_ratio: float | None


def assess_lower_band(scan: RangeScan, history: pd.DataFrame,
                      detector_config: RangeConfig,
                      config: LowerBandConfig | None = None) -> LowerBandContext:
    """Assess one already frozen detector result against its exact T-only input."""
    config = config or LowerBandConfig()
    frame = _validated_prefix(history, scan.decision_date, detector_config)
    if (scan.version != detector_config.version
            or scan.config_hash != detector_config.digest
            or scan.input_hash != canonical_hash(frame)
            or scan.decision_date != str(frame.date.iloc[-1].date())):
        raise ValueError("range scan and causal input/config do not match")
    for key, value in (("security_id", scan.security_id), ("source", scan.source),
                       ("basis", scan.basis), ("semantic_hash", scan.ri_semantic_hash)):
        if history.attrs.get(key) != value:
            raise ValueError("range scan and history provenance do not match")
    if scan.status_at_t != "CONFIRMED" or scan.best_active is None:
        return LowerBandContext(VERSION, config.digest, scan.detector,
                                scan.config_hash, scan.input_hash,
                                scan.decision_date, "NO_ACTIVE_RANGE",
                                ("no_confirmed_active_range",), None, None,
                                None, None, None, None, None, None)

    candidate = scan.best_active
    if (candidate.state_at_t != "CONFIRMED" or candidate.expired
            or candidate.first_knowable_at > scan.decision_date):
        raise ValueError("active range is not causally confirmed at T")
    close = frame.close.to_numpy(dtype=float)
    low = frame.low.to_numpy(dtype=float)
    volume = frame.volume.to_numpy(dtype=float)
    t_close = float(close[-1])
    position = float(candidate.current_position)
    floor = sum(candidate.support_zone)/2
    ceiling = sum(candidate.resistance_zone)/2
    if not np.isclose(position, (t_close-floor)/(ceiling-floor), rtol=1e-9, atol=1e-9):
        raise ValueError("active range position does not match T close")
    headroom = float(candidate.resistance_zone[0]/t_close - 1)
    last_day = float(t_close/close[-2] - 1)
    three_day = float(t_close/close[-4] - 1)
    recent_low = float(np.min(low[-3:])/np.min(low[-6:-3]) - 1)
    baseline_volume = float(np.median(volume[-20:-3]))
    volume_ratio = (float(np.mean(volume[-3:])/baseline_volume)
                    if baseline_volume > 0 else None)

    reasons = []
    if position < 0:
        reasons.append("below_geometric_floor")
    if position > config.max_position:
        reasons.append("away_from_lower_zone")
    if headroom < config.min_headroom:
        reasons.append("limited_headroom")
    if last_day > config.max_last_day_gain or three_day > config.max_three_day_gain:
        reasons.append("price_overextended")
    if last_day < config.min_last_day_return or recent_low < config.min_recent_low_change:
        reasons.append("decline_not_stabilized")
    if volume_ratio is None:
        reasons.append("volume_baseline_unavailable")
    elif volume_ratio > config.max_volume_ratio:
        reasons.append("volume_spike_review")

    if "below_geometric_floor" in reasons:
        state = "WAIT_UNDERCUT"
    elif "away_from_lower_zone" in reasons:
        state = "AWAY_FROM_LOWER"
    elif "limited_headroom" in reasons or "price_overextended" in reasons:
        state = "WAIT_PRICE"
    elif ("decline_not_stabilized" in reasons or "volume_baseline_unavailable" in reasons
          or "volume_spike_review" in reasons):
        state = "WAIT_STABILIZATION"
    else:
        state = "NEAR_LOWER_STABILIZING"
    return LowerBandContext(VERSION, config.digest, scan.detector,
                            scan.config_hash, scan.input_hash, scan.decision_date,
                            state, tuple(reasons), candidate.formation_start,
                            candidate.first_knowable_at, position, headroom,
                            last_day, three_day, recent_low, volume_ratio)

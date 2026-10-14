"""Lossless necessary conditions for the Stage C near-lower context.

This can only reject `NEAR_LOWER_STABILIZING`. It says nothing about box
existence, other lower-band states, structure quality, or future returns.
Unknown or untrusted recent input is always retained for the full detector.
"""
from __future__ import annotations

import numpy as np

from .lower_band import LowerBandConfig

VERSION = "box-near-lower-necessary-gate-v1"
EPSILON = 1e-10


def necessary_near_lower(
    close: list[float], low: list[float], volume: list[float],
    config: LowerBandConfig,
) -> tuple[bool, tuple[str, ...]]:
    """Return possible/necessary-rejection reasons using only the final 20 T bars.

    Exact metrics mirror `assess_lower_band`; margin only makes exclusion more
    conservative around floating-point boundaries. An unsafe prefix is not
    grounds for exclusion: the full RI v1 provider must handle it.
    """
    if not (len(close) == len(low) == len(volume) == 20):
        return True, ("unknown_recent_prefix",)
    try:
        c = np.asarray(close, dtype=float)
        lo = np.asarray(low, dtype=float)
        v = np.asarray(volume, dtype=float)
    except (TypeError, ValueError):
        return True, ("unknown_recent_prefix",)
    if (not np.isfinite(c).all() or not np.isfinite(lo).all()
            or not np.isfinite(v).all() or (c <= 0).any()
            or (lo <= 0).any() or (v < 0).any()):
        return True, ("unknown_recent_prefix",)
    last_day = float(c[-1]/c[-2] - 1)
    three_day = float(c[-1]/c[-4] - 1)
    recent_low = float(np.min(lo[-3:])/np.min(lo[-6:-3]) - 1)
    baseline = float(np.median(v[-20:-3]))
    reasons = []
    if last_day > config.max_last_day_gain + EPSILON:
        reasons.append("last_day_overextended")
    if three_day > config.max_three_day_gain + EPSILON:
        reasons.append("three_day_overextended")
    if last_day < config.min_last_day_return - EPSILON:
        reasons.append("last_day_declining")
    if recent_low < config.min_recent_low_change - EPSILON:
        reasons.append("recent_low_falling")
    if baseline <= 0:
        reasons.append("volume_baseline_unavailable")
    elif float(np.mean(v[-3:])/baseline) > config.max_volume_ratio + EPSILON:
        reasons.append("volume_spike")
    return not reasons, tuple(reasons)

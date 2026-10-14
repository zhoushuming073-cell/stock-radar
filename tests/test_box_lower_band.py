"""Causal lower-band context and fail-closed scan binding."""
from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest

from radar.box_labeling.lower_band import (
    LowerBandConfig, assess_lower_band,
)
from radar.box_labeling.range_detector import QuantileZoneDetector, RangeConfig


def bars(n=126):
    i = np.arange(n)
    center = 100 + 10*np.sin(i*2*np.pi/20)
    return pd.DataFrame({
        "date": pd.bdate_range("2023-01-02", periods=n),
        "open": center-.2, "high": center+1, "low": center-1,
        "close": center+.2, "volume": 1_000_000.,
    })


def evaluate(frame, config=None):
    detector_config = RangeConfig()
    scan = QuantileZoneDetector().detect(frame, frame.date.iloc[-1], detector_config)
    return assess_lower_band(scan, frame, detector_config, config)


def test_config_is_exact_and_versioned():
    config = LowerBandConfig()
    assert LowerBandConfig.from_mapping(asdict(config)) == config
    assert config.digest == LowerBandConfig().digest
    with pytest.raises(ValueError, match="keys"):
        LowerBandConfig.from_mapping({"version": config.version})
    with pytest.raises(ValueError, match="position"):
        LowerBandConfig(max_position=1.0)


def test_active_range_has_explainable_t_only_metrics():
    frame = bars()
    result = evaluate(frame)
    assert result.state in {"AWAY_FROM_LOWER", "WAIT_PRICE", "WAIT_STABILIZATION",
                            "NEAR_LOWER_STABILIZING", "WAIT_UNDERCUT"}
    assert result.formation_start <= result.range_known_at <= result.decision_date
    assert result.input_hash and result.config_hash and result.detector_config_hash
    assert result.position is not None
    assert result.headroom is not None
    assert result.volume_ratio == pytest.approx(1)


def test_no_active_range_cannot_become_entry_context():
    frame = bars()
    frame.loc[:, ["open", "high", "low", "close"]] = np.column_stack([
        50+.8*np.arange(len(frame))-.2, 51+.8*np.arange(len(frame)),
        49+.8*np.arange(len(frame)), 50+.8*np.arange(len(frame))+.2,
    ])
    result = evaluate(frame)
    assert result.state == "NO_ACTIVE_RANGE"
    assert result.position is None


def test_mismatched_scan_or_future_rows_are_rejected():
    frame = bars()
    config = RangeConfig()
    scan = QuantileZoneDetector().detect(frame, frame.date.iloc[-1], config)
    altered = frame.copy()
    altered.loc[125, "volume"] *= 3
    with pytest.raises(ValueError, match="do not match"):
        assess_lower_band(scan, altered, config)
    future = pd.concat([frame, bars(n=127).tail(1)], ignore_index=True)
    with pytest.raises(ValueError, match="post-T"):
        assess_lower_band(scan, future, config)
    with pytest.raises(ValueError, match="do not match"):
        assess_lower_band(scan, frame, RangeConfig(max_active_age=19))


def test_t_result_is_invariant_to_later_market_mutation():
    full = bars(130)
    t = full.date.iloc[125]
    prefix = full.loc[full.date.le(t)].copy()
    earlier = evaluate(prefix)
    full.loc[full.date.gt(t), ["open", "high", "low", "close", "volume"]] = [
        400, 500, 300, 450, 9e9,
    ]
    later = evaluate(full.loc[full.date.le(t)].copy())
    assert earlier == later


def test_extension_is_separate_from_structure():
    frame = bars()
    loose = LowerBandConfig(max_position=.99, min_headroom=.001,
                            max_last_day_gain=.001, max_three_day_gain=.001,
                            min_last_day_return=-.99, min_recent_low_change=-.99,
                            max_volume_ratio=100)
    result = evaluate(frame, loose)
    assert result.state == "WAIT_PRICE"
    assert "price_overextended" in result.reasons

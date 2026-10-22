"""Causal and negative controls for the two Stage A structure baselines."""
from dataclasses import asdict

import numpy as np
import pandas as pd
import pytest

from radar.box_labeling.range_detector import (
    ConfirmedPivotDetector, QuantileZoneDetector, RangeConfig, _independent,
    _pivot_geometry,
)


def bars(kind="range", n=126):
    i = np.arange(n)
    if kind == "range":
        center = 100 + 10*np.sin(i*2*np.pi/20)
    elif kind == "uptrend":
        center = 50 + .8*i
    elif kind == "downtrend":
        center = 150 - .8*i
    elif kind == "crash":
        center = np.r_[100 + 10*np.sin(i[:100]*2*np.pi/20),
                       np.linspace(85, 48, n-100)]
    elif kind == "one_sided":
        center = 100 + np.where(i%20 < 17, 0, 10)
    else:
        raise AssertionError(kind)
    return pd.DataFrame({
        "date": pd.bdate_range("2023-01-02", periods=n),
        "open": center-.2, "high": center+1, "low": center-1,
        "close": center+.2, "volume": 1_000_000.,
    })


DETECTORS = (QuantileZoneDetector(), ConfirmedPivotDetector())


def scan(detector, frame):
    return detector.detect(frame, frame.date.iloc[-1], RangeConfig())


def test_versioned_config_is_exact_and_reproducible():
    cfg = RangeConfig()
    assert RangeConfig.from_mapping(asdict(cfg)) == cfg
    assert cfg.digest == RangeConfig().digest
    with pytest.raises(ValueError, match="keys"):
        RangeConfig.from_mapping({"version": cfg.version})
    with pytest.raises(ValueError, match="window"):
        RangeConfig(window_lengths=(20, 180))
    with pytest.raises(ValueError, match="pivot"):
        RangeConfig(pivot_right=5)


@pytest.mark.parametrize("detector", DETECTORS, ids=lambda d: d.name)
def test_range_is_confirmed_with_independent_touches_and_causal_dates(detector):
    result = scan(detector, bars())
    assert result.status_at_t == "CONFIRMED"
    assert result.structure_exists_in_past and result.active_unbroken_box_at_t
    assert result.evaluated_windows > 1
    selected = result.best_active
    assert selected is not None
    assert selected.support_touches >= 2 and selected.resistance_touches >= 2
    assert selected.completed_alternations >= 3
    assert selected.formation_start <= selected.first_knowable_at <= result.decision_date
    assert selected.first_knowable_at == selected.window_end
    assert selected.support_zone[1] < selected.resistance_zone[0]
    assert all(t.event_date <= t.first_confirmable_at <= selected.first_knowable_at
               for t in selected.touches)
    if detector.name == "confirmed-pivot-zone-v1":
        assert all(t.event_date < t.first_confirmable_at for t in selected.touches)
    else:
        assert all(t.first_confirmable_at == selected.window_end for t in selected.touches)


@pytest.mark.parametrize("detector", DETECTORS, ids=lambda d: d.name)
def test_future_mutation_and_full_frame_rejection(detector):
    full = bars(n=150)
    t = full.date.iloc[125]
    prefix = full.loc[full.date.le(t)].copy()
    before = detector.detect(prefix, t)
    changed = full.copy()
    changed.loc[changed.date.gt(t), ["open", "high", "low", "close", "volume"]] = [
        800, 999, 700, 900, 5e9,
    ]
    after = detector.detect(changed.loc[changed.date.le(t)].copy(), t)
    assert before == after
    with pytest.raises(ValueError, match="post-T"):
        detector.detect(full, t)


def test_confirmed_pivot_requires_right_bars_and_never_retroactively_backdates():
    cfg = RangeConfig()
    f = bars(n=44)
    # A unique high whose three right bars are needed before it may be used.
    i = 40
    f.loc[i, ["open", "high", "low", "close"]] = [100, 112, 99, 100]
    earlier = _pivot_geometry(f.iloc[:i+3].reset_index(drop=True), cfg)
    later = _pivot_geometry(f.iloc[:i+4].reset_index(drop=True), cfg)
    assert earlier is not None and later is not None
    assert not any(t.side == "UPPER" and t.event_date == str(f.date.iloc[i].date())
                   for t in earlier[2])
    assert any(t.side == "UPPER" and t.event_date == str(f.date.iloc[i].date())
               and t.first_confirmable_at == str(f.date.iloc[i+3].date())
               for t in later[2])


def test_long_plateau_is_not_backdated_as_a_confirmed_pivot():
    f = bars(n=50)
    for i in range(39, 46):
        f.loc[i, ["open", "high", "low", "close"]] = [100, 112, 99, 100]
    geometry = _pivot_geometry(f, RangeConfig())
    assert geometry is not None
    assert not any(t.side == "UPPER" and pd.Timestamp(t.event_date) >= f.date.iloc[39]
                   for t in geometry[2])


def test_one_outside_bar_cannot_count_as_both_sides():
    dates = bars(n=42).date
    events = [(10, "LOWER", 90., 13), (10, "UPPER", 110., 13),
              (20, "LOWER", 90., 23)]
    touches = _independent(events, dates, 5)
    assert len(touches) == 1
    assert touches[0].event_date == str(dates.iloc[20].date())


@pytest.mark.parametrize("kind", ("uptrend", "downtrend"))
@pytest.mark.parametrize("detector", DETECTORS, ids=lambda d: d.name)
def test_monotonic_trends_are_not_confirmed_boxes(detector, kind):
    result = scan(detector, bars(kind))
    assert result.status_at_t == "NONE"
    assert not result.structure_exists_in_past
    assert not result.active_unbroken_box_at_t


@pytest.mark.parametrize("detector", DETECTORS, ids=lambda d: d.name)
def test_historical_box_can_be_broken_at_t(detector):
    result = scan(detector, bars("crash"))
    assert result.structure_exists_in_past
    assert not result.active_unbroken_box_at_t
    assert result.status_at_t == "BREAKDOWN"
    assert any(c.state_at_t == "BREAKDOWN" for c in result.candidates
               if c.formation_status == "CONFIRMED")
    assert all(c.state_at_t == "NONE" for c in result.candidates if c.expired)
    assert result.best_historical.first_knowable_at < result.decision_date


def test_independent_baselines_can_disagree_without_forced_intersection():
    f = bars("one_sided")
    q = scan(QuantileZoneDetector(), f)
    p = scan(ConfirmedPivotDetector(), f)
    assert q.structure_exists_in_past
    assert not p.structure_exists_in_past
    assert q.detector != p.detector


@pytest.mark.parametrize("bad", ("extra_column", "future", "duplicate", "nan",
                                  "bad_ohlc", "short"))
def test_invalid_or_future_inputs_fail_closed(bad):
    f = bars()
    t = f.date.iloc[-1]
    if bad == "extra_column":
        f["future_return"] = 1.
    elif bad == "future":
        t = f.date.iloc[-2]
    elif bad == "duplicate":
        f.loc[1, "date"] = f.date.iloc[0]
    elif bad == "nan":
        f.loc[0, "close"] = np.nan
    elif bad == "bad_ohlc":
        f.loc[0, "high"] = f.low.iloc[0] - 1
    elif bad == "short":
        f = f.iloc[:20]
        t = f.date.iloc[-1]
    with pytest.raises(ValueError):
        QuantileZoneDetector().detect(f, t)


def test_price_rescaling_preserves_structure_metrics_and_timing():
    f = bars()
    scaled = f.copy()
    for col in ("open", "high", "low", "close"):
        scaled[col] *= 7.
    for detector in DETECTORS:
        a, b = scan(detector, f), scan(detector, scaled)
        assert a.status_at_t == b.status_at_t
        assert a.structure_exists_in_past == b.structure_exists_in_past
        assert a.best_active.first_knowable_at == b.best_active.first_knowable_at
        assert b.best_active.support_zone[0] == pytest.approx(a.best_active.support_zone[0]*7)
        assert b.best_active.resistance_zone[1] == pytest.approx(a.best_active.resistance_zone[1]*7)

"""A Stage C target state must survive the separate Stage D necessary gate.

The simulated confirmed range isolates the implication from recognition
quality. It does not assert that any generated bar pattern is a real box.
"""
from hypothesis import given, settings, strategies as st
import numpy as np
import pandas as pd

from radar.box_labeling.fast_gate import necessary_near_lower
from radar.box_labeling.lower_band import LowerBandConfig, assess_lower_band
from radar.box_labeling.range_detector import RangeCandidate, RangeConfig, RangeScan
from radar.pit.shape import canonical_hash


def context_and_gate(c4: float, c2: float, c1: float,
                     prior_low: float, recent_low: float,
                     baseline_volume: float, recent_volume: float):
    close = np.full(126, 100.0)
    close[-4], close[-2], close[-1] = c4, c2, c1
    low = np.full(126, 80.0)
    low[-6:-3] = prior_low
    low[-3:] = recent_low
    volume = np.full(126, baseline_volume)
    volume[-3:] = recent_volume
    frame = pd.DataFrame({"date": pd.bdate_range("2024-01-01", periods=126),
                          "open": close, "high": close + 1,
                          "low": low, "close": close, "volume": volume})
    frame.attrs.update(security_id="synthetic", source="synthetic", basis="raw",
                       semantic_hash="synthetic-ri")
    detector_config = RangeConfig()
    context_config = LowerBandConfig()
    day = str(frame.date.iloc[-1].date())
    position = (float(close[-1]) - 80.0) / 30.0
    candidate = RangeCandidate(
        formation_start=str(frame.date.iloc[0].date()),
        window_end=str(frame.date.iloc[-5].date()),
        first_knowable_at=str(frame.date.iloc[-4].date()),
        formation_status="CONFIRMED", state_at_t="CONFIRMED",
        support_zone=(80.0, 80.0), resistance_zone=(110.0, 110.0),
        support_touches=2, resistance_touches=2, completed_alternations=3,
        touches=(), width_fraction=.3, occupancy=.8, center_drift=0.0,
        zone_stability=1.0, current_position=position, score=1.0,
        false_undercut_recovered=False, expired=False, rejection_reasons=())
    scan = RangeScan(
        detector="simulated-confirmed-range", version=detector_config.version,
        config_hash=detector_config.digest, input_hash=canonical_hash(frame),
        decision_date=day, security_id="synthetic", source="synthetic",
        basis="raw", ri_semantic_hash="synthetic-ri", evaluated_windows=1,
        formation_counts={}, rejection_counts={}, candidates=(candidate,),
        structure_exists_in_past=True, active_unbroken_box_at_t=True,
        status_at_t="CONFIRMED", best_historical=candidate, best_active=candidate)
    context = assess_lower_band(scan, frame, detector_config, context_config)
    possible, reasons = necessary_near_lower(
        close[-20:].tolist(), low[-20:].tolist(), volume[-20:].tolist(),
        context_config)
    return context, possible, reasons


def test_positive_stage_c_state_reaches_full_detector():
    context, possible, reasons = context_and_gate(
        88.0, 88.0, 88.0, 79.0, 79.0, 1000.0, 1000.0)
    assert context.state == "NEAR_LOWER_STABILIZING"
    assert possible and not reasons


@settings(max_examples=200, deadline=None, derandomize=True)
@given(c4=st.floats(min_value=85, max_value=105, allow_nan=False),
       c2=st.floats(min_value=85, max_value=105, allow_nan=False),
       c1=st.floats(min_value=85, max_value=105, allow_nan=False),
       prior_low=st.floats(min_value=70, max_value=83, allow_nan=False),
       recent_low=st.floats(min_value=70, max_value=83, allow_nan=False),
       baseline_volume=st.floats(min_value=0, max_value=5000, allow_nan=False),
       recent_volume=st.floats(min_value=0, max_value=10000, allow_nan=False))
def test_stage_c_target_implies_necessary_gate_possible(
        c4, c2, c1, prior_low, recent_low, baseline_volume, recent_volume):
    context, possible, reasons = context_and_gate(
        c4, c2, c1, prior_low, recent_low, baseline_volume, recent_volume)
    if context.state == "NEAR_LOWER_STABILIZING":
        assert possible, reasons

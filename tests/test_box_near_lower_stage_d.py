"""Candidate-only retrieval preserves the necessary gate and private receipt."""
from __future__ import annotations

import pytest

from radar.box_labeling.lower_band import LowerBandConfig
from scripts.scan_box_near_lower_stage_d import (
    TARGET, _check_payload, near_chunk, select_candidates,
)


def _prefix(security_id: str, close=None):
    return {"security_id": security_id, "n": 20,
            "distinct_sessions": 20, "distinct_dates": 20,
            "first_session": 1, "last_session": 20, "session_no": 20,
            "last_date": "2024-07-01", "decision_date": "2024-07-01",
            "trusted": True, "closes": close or [100.0]*20,
            "lows": [98.0]*20, "volumes": [1000.0]*20}


def test_selection_keeps_order_unknown_and_only_rejects_certainly_not():
    rows = [{"security_id": id_} for id_ in ("A", "B", "C")]
    b = _prefix("B", [100.0]*19+[90.0])
    c = _prefix("C")
    c["trusted"] = False
    selected, receipt = select_candidates(rows, [_prefix("A"), b, c], LowerBandConfig())
    assert [row["security_id"] for row in selected] == ["A", "C"]
    assert (receipt["eligible"], receipt["possible"], receipt["certainly_not"],
            receipt["unknown_retained"]) == (3, 2, 1, 1)
    assert "last_day_declining" in receipt["rejection_reasons_overlapping"]


def test_selection_fails_closed_on_missing_duplicate_or_extra_prefix():
    rows = [{"security_id": "A"}]
    for prefixes in ([], [_prefix("A"), _prefix("A")],
                     [_prefix("A"), _prefix("B")]):
        with pytest.raises(ValueError, match="recent-prefix query"):
            select_candidates(rows, prefixes, LowerBandConfig())


def test_near_chunk_discards_other_states(monkeypatch):
    def fake_scan(provider, day, rows, detector_config, context_config):
        return {"requested": 1, "processed": 1, "excluded": [],
                "contexts": [{"security_id": "A", "source": "S",
                              "detectors": {"q": {"state": TARGET},
                                            "p": {"state": "WAIT_PRICE"}}}]}
    monkeypatch.setattr("scripts.scan_box_near_lower_stage_d.scan_chunk", fake_scan)
    payload = near_chunk(None, "2024-07-01", [{"security_id": "A"}], None, None)
    assert set(payload["near_contexts"][0]["detectors"]) == {"q"}


def test_receipt_rejects_wrong_state_and_count():
    group = [{"security_id": "A"}]
    context = {"state": TARGET, "detector": "q", "decision_date": "2024-07-01",
               "config_hash": "context", "detector_config_hash": "detector"}
    payload = {"requested": 1, "processed": 1, "excluded": [],
               "decision_date": "2024-07-01", "context_config_hash": "context",
               "detector_config_hash": "detector",
               "near_contexts": [{"security_id": "A", "detectors": {"q": context}}]}
    _check_payload(payload, group)
    payload["near_contexts"][0]["detectors"]["q"]["state"] = "WAIT_PRICE"
    with pytest.raises(ValueError, match="provenance/state"):
        _check_payload(payload, group)
    payload["near_contexts"] = []
    payload["processed"] = 0
    with pytest.raises(ValueError, match="count or identity"):
        _check_payload(payload, group)

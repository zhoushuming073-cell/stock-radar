import hashlib
import json

import pandas as pd
import pytest

from radar.pit.quant_execution_closure import (
    compare_overlap, inspect_bars, public_summary, required_sessions, verify_acquisition,
)


def prices():
    return pd.DataFrame([{"date": "2023-01-17", "open": 10., "high": 11., "low": 9.,
                          "close": 10.5, "volume": 100., "source": "original", "basis": "split"}])


def check(frame):
    return inspect_bars(frame, ["2023-01-17"], source="original", basis="split")


def test_exact_holding_sessions_skip_holiday_but_include_all_tradable_days():
    result = required_sessions(["2023-01-13"], ["2023-01-03", "2023-01-13", "2023-02-01"])
    assert result["2023-01-13"]["entry"] == "2023-01-17"
    assert result["2023-01-13"]["exit"] == "2023-01-30"
    assert len(result["2023-01-13"]["sessions"]) == 10


@pytest.mark.parametrize("decision", ["2023-01-14", "2023-01-02", "2023-02-01"])
def test_no_unregistered_or_nontrading_decision(decision):
    with pytest.raises(ValueError):
        required_sessions([decision], ["2023-01-03", "2023-01-13", "2023-02-01"])


def test_cannot_shorten_incomplete_exit_horizon():
    with pytest.raises(ValueError):
        required_sessions(["2023-01-13"], ["2023-01-03", "2023-01-13", "2023-01-18"])


def test_unrelated_future_rows_cannot_change_dependency_audit():
    f = prices()
    future = f.assign(date="2025-01-17", open=1., high=2., low=1., close=1.)
    assert check(f) == check(pd.concat([f, future]))


def test_a_complete_download_does_not_assert_trust():
    result = check(prices())
    assert result["coverage_and_sanity_complete"]
    assert result["trust_acceptance"] == "NOT_ASSERTED"


def test_missing_no_trade_day_is_not_fill_forward():
    result = check(prices().iloc[:0])
    assert result["missing"] == ["2023-01-17"]
    assert result["available"] == 0
    assert not result["coverage_and_sanity_complete"]


def test_duplicate_source_dates_rejected():
    with pytest.raises(ValueError):check(pd.concat([prices(), prices()]))


@pytest.mark.parametrize("field,value", [("source", "new-provider"), ("basis", "raw")])
def test_same_ticker_and_date_do_not_allow_source_or_basis_switch(field, value):
    f = prices();f[field] = value
    assert not check(f)["coverage_and_sanity_complete"]


@pytest.mark.parametrize("column", ["identity_conflict", "class_or_name_boundary", "future_leakage"])
def test_identity_and_leakage_flags_never_silently_promoted(column):
    f = prices();f[column] = True
    assert check(f)["unsafe"] == ["2023-01-17"]


def test_bad_ohlcv_cannot_be_accepted_from_complete_download():
    f = prices();f["low"] = 20.
    assert not check(f)["coverage_and_sanity_complete"]


def test_zero_volume_is_preserved_as_observation_not_imputed_trade():
    f = prices();f["volume"] = 0
    result = check(f)
    assert result["available"] == 1
    assert result["trust_acceptance"] == "NOT_ASSERTED"


def test_matching_close_is_not_ohlcv_equivalence():
    incoming = prices();incoming["volume"] = 127.
    result = compare_overlap(prices(), incoming)
    assert result["exact_by_field"]["close"]
    assert not result["exact_by_field"]["volume"]
    assert not result["all_ohlcv_exact"]


def test_no_overlap_cannot_certify_adjustment_units():
    assert not compare_overlap(prices(), prices().assign(date="2023-01-18"))["all_ohlcv_exact"]


def test_two_timestamps_on_same_daily_session_cannot_multiply_overlap():
    incoming = pd.concat([prices().assign(date="2023-01-17T00:00:00"),
                          prices().assign(date="2023-01-17T16:00:00")])
    with pytest.raises(ValueError, match="duplicate daily sessions"):
        compare_overlap(prices(), incoming)


def test_bound_raw_bytes_replay_and_tamper_detection(tmp_path):
    p = tmp_path / "capture.raw";p.write_bytes(b"original source")
    r = {"file": str(p), "raw_sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
    assert verify_acquisition(tmp_path, r) == b"original source"
    p.write_bytes(b"modified")
    with pytest.raises(ValueError):verify_acquisition(tmp_path, r)


def test_acquisition_file_cannot_escape_private_version_directory(tmp_path):
    base = tmp_path / "version";base.mkdir()
    p = tmp_path / "outside.raw";p.write_bytes(b"source")
    with pytest.raises(ValueError):
        verify_acquisition(base, {"file": str(p), "raw_sha256": hashlib.sha256(p.read_bytes()).hexdigest()})


def test_public_summary_does_not_publish_private_security_evidence():
    records = [{"security_id": "PRIVATE", "historical_symbol": "SECRET", "gate_reason": "missing_prices",
                "price_check": {"missing": ["2023-01-17"], "unsafe": []}, "raw_bars": [prices().to_dict()],
                "accepted_supplement": False}]
    result = public_summary(records)
    assert result["status"] == "BLOCKED"
    assert result["missing_session_count"] == 1
    assert "PRIVATE" not in json.dumps(result) and "SECRET" not in json.dumps(result)

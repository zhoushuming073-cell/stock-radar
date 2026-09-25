"""Behavioral tests for the Phase 1B Pydantic models."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from radar.models import (
    AssetRecord,
    DailyBar,
    IngestionResult,
    ProviderBatchResult,
    ValidationIssue,
)

UTC = timezone.utc
# US/Eastern offset used by the tests so they never depend on a tz database.
EASTERN = timezone(timedelta(hours=-5))


def make_bar(**overrides) -> DailyBar:
    payload = {
        "symbol": "AAPL",
        "date": date(2024, 1, 5),
        "open": 10.0,
        "high": 11.0,
        "low": 9.5,
        "close": 10.5,
        "volume": 1_000,
        "provider": "alpaca",
        "feed": "sip",
        "adjustment": "split",
        "downloaded_at": datetime(2024, 1, 6, 2, 0, tzinfo=UTC),
    }
    payload.update(overrides)
    return DailyBar(**payload)


def make_asset(**overrides) -> AssetRecord:
    payload = {
        "symbol": "AAPL",
        "asset_class": "us_equity",
        "status": "active",
        "tradable": True,
        "fractionable": True,
        "shortable": True,
        "easy_to_borrow": True,
        "first_seen": datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
        "last_seen": datetime(2024, 1, 2, 12, 0, tzinfo=UTC),
        "updated_at": datetime(2024, 1, 3, 12, 0, tzinfo=UTC),
    }
    payload.update(overrides)
    return AssetRecord(**payload)


# --- symbols ---------------------------------------------------------------


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("aapl", "AAPL"),
        ("  msft  ", "MSFT"),
        ("brk.b", "BRK.B"),
        ("rds-a", "RDS-A"),
    ],
)
def test_symbol_normalization(raw, expected):
    assert make_bar(symbol=raw).symbol == expected


@pytest.mark.parametrize("raw", ["", "   ", "AAPL!", "A/B", "AAPL..B", 123])
def test_invalid_symbol_rejected(raw):
    with pytest.raises(ValidationError):
        make_bar(symbol=raw)


# --- datetimes -------------------------------------------------------------


def test_downloaded_at_normalized_to_utc():
    bar = make_bar(downloaded_at=datetime(2024, 1, 6, 2, 0, tzinfo=EASTERN))
    assert bar.downloaded_at.tzinfo == UTC
    assert bar.downloaded_at == datetime(2024, 1, 6, 7, 0, tzinfo=UTC)


def test_naive_downloaded_at_rejected():
    with pytest.raises(ValidationError):
        make_bar(downloaded_at=datetime(2024, 1, 6, 2, 0))


def test_asset_timestamps_normalized_to_utc():
    asset = make_asset(
        first_seen=datetime(2024, 1, 1, 9, 30, tzinfo=EASTERN),
        last_seen=datetime(2024, 1, 2, 9, 30, tzinfo=EASTERN),
        updated_at=datetime(2024, 1, 3, 9, 30, tzinfo=EASTERN),
    )
    assert asset.first_seen == datetime(2024, 1, 1, 14, 30, tzinfo=UTC)
    assert asset.last_seen == datetime(2024, 1, 2, 14, 30, tzinfo=UTC)
    assert asset.updated_at == datetime(2024, 1, 3, 14, 30, tzinfo=UTC)


def test_naive_asset_timestamp_rejected():
    with pytest.raises(ValidationError):
        make_asset(updated_at=datetime(2024, 1, 3, 12, 0))


# --- US/Eastern session date ----------------------------------------------


def test_eastern_session_date_preserved_even_when_utc_date_differs():
    """A 21:00 ET retrieval is already the next UTC day; the session date must not move."""
    eastern_download = datetime(2024, 1, 5, 21, 0, tzinfo=EASTERN)
    bar = make_bar(
        date=eastern_download.date(),
        downloaded_at=eastern_download.astimezone(UTC),
    )
    assert bar.date == date(2024, 1, 5)
    assert bar.downloaded_at.date() == date(2024, 1, 6)


def test_datetime_rejected_for_session_date():
    with pytest.raises(ValidationError):
        make_bar(date=datetime(2024, 1, 5, 21, 0, tzinfo=UTC))


# --- OHLCV ----------------------------------------------------------------


@pytest.mark.parametrize(
    "field,value",
    [
        ("open", 0.0),
        ("open", -1.0),
        ("high", 0.0),
        ("low", -0.01),
        ("close", 0.0),
        ("vwap", -5.0),
        ("vwap", 0.0),
    ],
)
def test_non_positive_prices_rejected(field, value):
    with pytest.raises(ValidationError):
        make_bar(**{field: value})


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_finite_prices_rejected(bad):
    with pytest.raises(ValidationError):
        make_bar(high=bad)


@pytest.mark.parametrize(
    "overrides",
    [
        {"high": 9.0},  # high < low and < open/close
        {"high": 10.1},  # high < open
        {"high": 10.4},  # high < close
        {"low": 10.1},  # low > open
        {"low": 9.8, "close": 9.75},  # low > close
    ],
)
def test_ohlc_consistency_enforced(overrides):
    with pytest.raises(ValidationError):
        make_bar(**overrides)


@pytest.mark.parametrize("field", ["volume", "trade_count"])
def test_counts_must_be_non_negative(field):
    with pytest.raises(ValidationError):
        make_bar(**{field: -1})


@pytest.mark.parametrize("field", ["volume", "trade_count"])
def test_counts_must_be_integral(field):
    with pytest.raises(ValidationError):
        make_bar(**{field: 1.5})


def test_optional_fields_default_to_none():
    bar = make_bar()
    assert bar.vwap is None
    assert bar.trade_count is None
    assert bar.timeframe == "1Day"


def test_invalid_timeframe_rejected():
    with pytest.raises(ValidationError):
        make_bar(timeframe="1Hour")


def test_missing_provenance_rejected():
    with pytest.raises(ValidationError):
        make_bar(provider="  ")


def test_unknown_field_rejected():
    with pytest.raises(ValidationError):
        make_bar(extra_field=1)


# --- AssetRecord -----------------------------------------------------------


def test_asset_record_requires_ordered_timestamps():
    with pytest.raises(ValidationError):
        make_asset(
            first_seen=datetime(2024, 1, 5, tzinfo=UTC),
            last_seen=datetime(2024, 1, 4, tzinfo=UTC),
        )
    with pytest.raises(ValidationError):
        make_asset(
            last_seen=datetime(2024, 1, 9, tzinfo=UTC),
            updated_at=datetime(2024, 1, 8, tzinfo=UTC),
        )


def test_asset_record_requires_flags():
    payload = {
        "symbol": "AAPL",
        "asset_class": "us_equity",
        "status": "active",
        "tradable": True,
        "fractionable": True,
        "shortable": True,
    }
    with pytest.raises(ValidationError):
        AssetRecord(
            first_seen=datetime(2024, 1, 1, tzinfo=UTC),
            last_seen=datetime(2024, 1, 1, tzinfo=UTC),
            updated_at=datetime(2024, 1, 1, tzinfo=UTC),
            **payload,
        )


def test_asset_record_optional_name_and_exchange():
    asset = make_asset()
    assert asset.name is None
    assert asset.exchange is None


# --- ValidationIssue -------------------------------------------------------


def test_validation_issue_defaults_and_normalization():
    issue = ValidationIssue(
        code="high_below_low", message="high must be >= low", severity="error"
    )
    assert issue.details == {}
    assert issue.symbol is None
    assert issue.date is None

    issue = ValidationIssue(
        code="gap",
        message="missing session",
        severity="warning",
        symbol=" aapl ",
        date=date(2024, 1, 5),
    )
    assert issue.symbol == "AAPL"


@pytest.mark.parametrize(
    "overrides",
    [{"severity": "critical"}, {"code": ""}, {"message": "  "}],
)
def test_validation_issue_rejects_bad_values(overrides):
    payload = {"code": "x", "message": "y", "severity": "warning"}
    payload.update(overrides)
    with pytest.raises(ValidationError):
        ValidationIssue(**payload)


# --- ProviderBatchResult ---------------------------------------------------


def make_batch(**overrides) -> ProviderBatchResult:
    payload = {
        "requested_symbols": ["AAPL", "MSFT", "TSLA"],
        "provider": "alpaca",
        "feed": "sip",
        "start": date(2024, 1, 2),
        "end": date(2024, 1, 5),
    }
    payload.update(overrides)
    return ProviderBatchResult(**payload)


def test_partial_batch_is_valid_without_failed_symbols():
    """Missing bars for a session are not automatically a failure."""
    batch = make_batch(bars=[make_bar(symbol="AAPL")])
    assert len(batch.bars) == 1
    assert batch.failed_symbols == {}
    assert batch.issues == []


def test_batch_accepts_explicit_failures_and_normalizes_keys():
    batch = make_batch(
        bars=[make_bar(symbol="AAPL")],
        failed_symbols={" msft ": "symbol not found"},
        issues=[
            ValidationIssue(
                code="empty_bars", message="no bars returned", severity="warning"
            )
        ],
    )
    assert batch.failed_symbols == {"MSFT": "symbol not found"}
    assert len(batch.issues) == 1


def test_requested_symbols_deduped_and_normalized():
    batch = make_batch(requested_symbols=["aapl", " AAPL ", "msft"])
    assert batch.requested_symbols == ["AAPL", "MSFT"]


def test_batch_rejects_reversed_date_range():
    with pytest.raises(ValidationError):
        make_batch(start=date(2024, 1, 5), end=date(2024, 1, 2))


def test_batch_rejects_empty_failure_reason():
    with pytest.raises(ValidationError):
        make_batch(failed_symbols={"AAPL": "  "})


def test_batch_rejects_empty_bars_symbol_mismatch_of_type():
    with pytest.raises(ValidationError):
        make_batch(bars=[{"symbol": "AAPL"}])


# --- IngestionResult -------------------------------------------------------


def make_ingestion(**overrides) -> IngestionResult:
    payload = {
        "fetched_rows": 100,
        "inserted_rows": 60,
        "updated_rows": 20,
        "unchanged_rows": 15,
        "rejected_rows": 5,
        "batch_count": 4,
    }
    payload.update(overrides)
    return IngestionResult(**payload)


def test_ingestion_result_defaults():
    result = make_ingestion()
    assert result.issues == []
    assert result.failed_symbols == {}


def test_ingestion_result_accepts_exact_accounting():
    assert make_ingestion().fetched_rows == 100


def test_ingestion_result_rejects_over_accounting():
    with pytest.raises(ValidationError):
        make_ingestion(rejected_rows=10)


def test_ingestion_result_rejects_negative_counts():
    with pytest.raises(ValidationError):
        make_ingestion(inserted_rows=-1)


def test_ingestion_result_normalizes_failed_symbol_keys():
    result = make_ingestion(failed_symbols={" tsla ": "timeout"})
    assert result.failed_symbols == {"TSLA": "timeout"}

"""Behavioral checks for Phase 1G bar validation."""

from __future__ import annotations

from datetime import date, datetime, timezone

from radar.models import DailyBar
from radar.db import get_connection
from radar.validation.bars import validate_daily_bars, validate_database

UTC = timezone.utc


def bar(day: int, *, close: float = 10.0) -> DailyBar:
    return DailyBar(
        symbol="AAPL",
        date=date(2024, 1, day),
        open=close,
        high=close + 1,
        low=close - 1,
        close=close,
        volume=1000,
        provider="alpaca",
        feed="sip",
        adjustment="split",
        downloaded_at=datetime(2024, 1, 12, tzinfo=UTC),
    )


def test_bad_ohlc_missing_field_and_negative_volume_rejected() -> None:
    first = bar(2).model_dump()
    high_below_low = {**first, "high": 1.0}
    missing_close = {key: value for key, value in first.items() if key != "close"}
    negative_volume = {**first, "volume": -1}
    valid, summary = validate_daily_bars(
        [high_below_low, missing_close, negative_volume, first]
    )
    assert len(valid) == 1
    assert (summary.checked_rows, summary.accepted_rows, summary.rejected_rows) == (4, 1, 3)
    assert {issue.code for issue in summary.issues} == {"invalid_bar", "missing_field"}


def test_duplicate_symbol_date_rejected() -> None:
    valid, summary = validate_daily_bars([bar(2), bar(2)])
    assert len(valid) == 1
    assert summary.rejected_rows == 1
    assert summary.issues[0].code == "duplicate_symbol_date"


def test_large_jump_warned_but_not_auto_rejected() -> None:
    valid, summary = validate_daily_bars([bar(2), bar(3, close=20.0)])
    assert len(valid) == 2
    assert summary.rejected_rows == 0
    assert [issue.code for issue in summary.issues] == ["abnormal_price_jump"]


def test_missing_market_session_and_stale_ticker_flagged() -> None:
    sessions = [date(2024, 1, day) for day in (2, 3, 4, 5, 8, 9, 10, 11, 12)]
    _, summary = validate_daily_bars(
        [bar(2), bar(4)], expected_sessions=sessions, stale_after_sessions=5
    )
    assert ("missing_trading_session", date(2024, 1, 3)) in {
        (issue.code, issue.date) for issue in summary.issues
    }
    assert "stale_ticker" in {issue.code for issue in summary.issues}


def test_database_validation_flags_corrupt_row_and_empty_ticker() -> None:
    connection = get_connection(":memory:")
    connection.execute(
        """INSERT INTO daily_bars
        (symbol, date, open, high, low, close, volume, provider, feed,
         adjustment, downloaded_at)
        VALUES ('AAPL', '2024-01-02', 10, 11, 9, -1, 100,
                'alpaca', 'sip', 'split', '2024-01-03T00:00:00Z')"""
    )
    summary = validate_database(
        connection, ["AAPL", "MSFT"], [date(2024, 1, 2)]
    )
    assert summary.checked_rows == 1
    assert summary.rejected_rows == 1
    assert {issue.code for issue in summary.issues} == {"invalid_bar", "no_bars"}

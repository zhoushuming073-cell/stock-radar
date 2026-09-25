"""Offline tests for missing-session planning and restartable ingestion."""

from __future__ import annotations

from datetime import date, datetime, timezone

import pytest

from radar.db import get_connection
from radar.ingestion.bars import DownloadWindow, ingest_daily_bars, plan_missing_windows
from radar.models import DailyBar, ProviderBatchResult

UTC = timezone.utc
SESSIONS = [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)]


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[tuple[str, ...], date, date, str, str]] = []
        self.fail: set[str] = set()

    def get_daily_bars(self, symbols, start, end, feed, adjustment):
        self.calls.append((tuple(symbols), start, end, feed, adjustment))
        bars = []
        for symbol in symbols:
            if symbol in self.fail:
                continue
            for day in SESSIONS:
                if start <= day <= end:
                    bars.append(
                        DailyBar(
                            symbol=symbol,
                            date=day,
                            open=10.0,
                            high=11.0,
                            low=9.0,
                            close=10.5,
                            volume=1000,
                            provider="alpaca",
                            feed=feed,
                            adjustment=adjustment,
                            downloaded_at=datetime(2024, 1, 6, tzinfo=UTC),
                        )
                    )
        yield ProviderBatchResult(
            requested_symbols=list(symbols),
            bars=bars,
            failed_symbols={symbol: "fake failure" for symbol in symbols if symbol in self.fail},
            provider="alpaca",
            feed=feed,
            start=start,
            end=end,
        )


def test_initial_load_then_no_network_on_identical_rerun() -> None:
    connection = get_connection(":memory:")
    provider = FakeProvider()
    first = ingest_daily_bars(
        connection, provider, ["AAPL", "MSFT"], SESSIONS, feed="sip"
    )
    assert (first.fetched_rows, first.inserted_rows, first.batch_count) == (6, 6, 1)
    assert provider.calls == [(('AAPL', 'MSFT'), SESSIONS[0], SESSIONS[-1], 'sip', 'split')]
    second = ingest_daily_bars(
        connection, provider, ["AAPL", "MSFT"], SESSIONS, feed="sip"
    )
    assert second.fetched_rows == 0
    assert second.batch_count == 0
    assert len(provider.calls) == 1


def test_only_missing_single_ticker_session_is_requested() -> None:
    connection = get_connection(":memory:")
    provider = FakeProvider()
    ingest_daily_bars(connection, provider, ["AAPL", "MSFT"], SESSIONS, feed="sip")
    connection.execute("DELETE FROM daily_bars WHERE symbol='MSFT' AND date=?", [SESSIONS[1]])
    assert plan_missing_windows(connection, ["AAPL", "MSFT"], SESSIONS) == [
        DownloadWindow(SESSIONS[1], SESSIONS[1], ("MSFT",))
    ]
    result = ingest_daily_bars(
        connection, provider, ["AAPL", "MSFT"], SESSIONS, feed="sip"
    )
    assert result.inserted_rows == 1
    assert provider.calls[-1][:3] == (("MSFT",), SESSIONS[1], SESSIONS[1])


def test_one_failed_symbol_does_not_lose_other_bars() -> None:
    connection = get_connection(":memory:")
    provider = FakeProvider()
    provider.fail.add("MSFT")
    result = ingest_daily_bars(
        connection, provider, ["AAPL", "MSFT"], SESSIONS, feed="sip"
    )
    assert result.inserted_rows == 3
    assert result.failed_symbols == {"MSFT": "fake failure"}
    assert connection.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0] == 3
    assert plan_missing_windows(connection, ["AAPL", "MSFT"], SESSIONS)[0].symbols == ("MSFT",)


def test_changing_feed_is_rejected_before_any_network_request() -> None:
    connection = get_connection(":memory:")
    provider = FakeProvider()
    ingest_daily_bars(connection, provider, ["AAPL"], SESSIONS, feed="sip")
    before = len(provider.calls)
    with pytest.raises(ValueError, match="different provider/feed/adjustment"):
        ingest_daily_bars(connection, provider, ["AAPL"], SESSIONS, feed="iex")
    assert len(provider.calls) == before

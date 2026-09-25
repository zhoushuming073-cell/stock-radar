"""Offline failure-path tests for the Alpaca adapter."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest
from alpaca.common.exceptions import APIError
from requests.exceptions import Timeout

from radar.providers.alpaca import AlpacaProvider, ProviderError

UTC = timezone.utc


def api_error(status: int) -> APIError:
    return APIError("error", SimpleNamespace(response=SimpleNamespace(status_code=status)))


class FakeData:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def get_stock_bars(self, request):
        symbols = list(request.symbol_or_symbols)
        self.calls.append(symbols)
        if "BAD" in symbols:
            raise api_error(400)
        return SimpleNamespace(data={})


def provider(data, *, attempts: int = 2, waits: list[float] | None = None):
    waits = [] if waits is None else waits
    return AlpacaProvider(
        SimpleNamespace(),
        data,
        batch_size=3,
        max_attempts=attempts,
        sleep=waits.append,
        now=lambda: datetime(2024, 1, 7, tzinfo=UTC),
    )


def test_bad_symbol_isolated_without_losing_other_symbols() -> None:
    data = FakeData()
    result = list(
        provider(data).get_daily_bars(
            ["AAPL", "BAD", "MSFT"], date(2024, 1, 2), date(2024, 1, 5), "sip"
        )
    )
    assert len(result) == 1
    assert result[0].requested_symbols == ["AAPL", "BAD", "MSFT"]
    assert result[0].failed_symbols == {"BAD": "Alpaca HTTP 400"}
    assert ["AAPL", "BAD", "MSFT"] in data.calls
    assert ["AAPL"] in data.calls
    assert ["MSFT"] in data.calls


def test_access_denial_never_falls_back_to_another_feed() -> None:
    class Denied:
        def get_stock_bars(self, request):
            raise api_error(403)

    with pytest.raises(ProviderError, match="feed sip"):
        list(provider(Denied()).get_daily_bars(["AAPL"], date(2024, 1, 2), date(2024, 1, 5), "sip"))


def test_request_timeout_is_retried_then_reported_per_batch() -> None:
    class TimedOut:
        calls = 0

        def get_stock_bars(self, request):
            self.calls += 1
            raise Timeout("offline fake timeout")

    data = TimedOut()
    waits: list[float] = []
    result = list(
        provider(data, attempts=3, waits=waits).get_daily_bars(
            ["AAPL", "MSFT"], date(2024, 1, 2), date(2024, 1, 5), "sip"
        )
    )
    assert data.calls == 3
    assert waits == [1, 2]
    assert set(result[0].failed_symbols) == {"AAPL", "MSFT"}


def test_rate_limit_retries_without_changing_feed() -> None:
    class Throttled:
        calls = 0

        def get_stock_bars(self, request):
            self.calls += 1
            if self.calls == 1:
                raise api_error(429)
            return SimpleNamespace(data={})

    data = Throttled()
    waits: list[float] = []
    result = list(
        provider(data, waits=waits).get_daily_bars(
            ["AAPL"], date(2024, 1, 2), date(2024, 1, 5), "sip"
        )
    )
    assert data.calls == 2
    assert waits == [1]
    assert result[0].feed == "sip"
    assert result[0].failed_symbols == {}

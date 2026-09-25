"""Pin the installed alpaca-py pagination behavior used by our provider."""

from __future__ import annotations

from datetime import datetime, timezone

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame


def test_alpaca_sdk_collects_all_bar_pages(monkeypatch) -> None:
    client = StockHistoricalDataClient("fake-key", "fake-secret")
    tokens: list[str | None] = []

    def fake_get(*, path, data):
        assert path == "/stocks/bars"
        assert data["feed"] == "sip"
        tokens.append(data.get("page_token"))
        bar = {
            "t": "2024-01-05T05:00:00Z" if len(tokens) == 1 else "2024-01-06T05:00:00Z",
            "o": 10.0,
            "h": 11.0,
            "l": 9.0,
            "c": 10.5,
            "v": 1000,
            "n": 100,
            "vw": 10.2,
        }
        return {
            "bars": {"AAPL": [bar]},
            "next_page_token": "second" if len(tokens) == 1 else None,
        }

    monkeypatch.setattr(client, "get", fake_get)
    request = StockBarsRequest(
        symbol_or_symbols=["AAPL"],
        timeframe=TimeFrame.Day,
        start=datetime(2024, 1, 5, tzinfo=timezone.utc),
        end=datetime(2024, 1, 7, tzinfo=timezone.utc),
        feed=DataFeed.SIP,
        adjustment=Adjustment.SPLIT,
    )
    result = client.get_stock_bars(request)
    assert tokens == [None, "second"]
    assert len(result.data["AAPL"]) == 2

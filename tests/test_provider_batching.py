"""Offline successful-path tests for Alpaca batching and timestamp mapping."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.enums import AssetClass, AssetStatus

from radar.providers.alpaca import AlpacaProvider

UTC = timezone.utc


class FakeTrading:
    request = None

    def get_all_assets(self, request):
        self.request = request
        return [
            SimpleNamespace(
                symbol="aapl",
                name="Apple",
                exchange="NASDAQ",
                asset_class=AssetClass.US_EQUITY,
                status=AssetStatus.ACTIVE,
                tradable=True,
                fractionable=True,
                shortable=True,
                easy_to_borrow=True,
            )
        ]


class FakeData:
    def __init__(self, bars=None):
        self.requests = []
        self.bars = {} if bars is None else bars

    def get_stock_bars(self, request):
        self.requests.append(request)
        return SimpleNamespace(data=self.bars)


def make_provider(data=None, batch_size=2):
    trading = FakeTrading()
    data = FakeData() if data is None else data
    return (
        AlpacaProvider(
            trading,
            data,
            batch_size=batch_size,
            sleep=lambda _: None,
            now=lambda: datetime(2024, 1, 7, tzinfo=UTC),
        ),
        trading,
        data,
    )


def test_active_us_equity_asset_request_and_mapping() -> None:
    adapter, trading, _ = make_provider()
    assets = adapter.get_assets()
    assert trading.request.asset_class == AssetClass.US_EQUITY
    assert trading.request.status == AssetStatus.ACTIVE
    assert [asset.symbol for asset in assets] == ["AAPL"]
    assert assets[0].first_seen.tzinfo == UTC


def test_batched_requests_keep_feed_adjustment_and_dates() -> None:
    adapter, _, data = make_provider(batch_size=2)
    result = list(
        adapter.get_daily_bars(
            ["AAPL", "MSFT", "TSLA", "NVDA", "AMZN"],
            date(2024, 1, 2),
            date(2024, 1, 5),
            "sip",
        )
    )
    assert [batch.requested_symbols for batch in result] == [
        ["AAPL", "MSFT"], ["TSLA", "NVDA"], ["AMZN"]
    ]
    assert all(batch.bars == [] and batch.failed_symbols == {} for batch in result)
    for request in data.requests:
        assert request.feed == DataFeed.SIP
        assert request.adjustment == Adjustment.SPLIT
        assert str(request.timeframe) == str(TimeFrame.Day)
        assert request.start == datetime(2024, 1, 2, 5)
        assert request.end == datetime(2024, 1, 5, 5)


def test_provider_bar_uses_new_york_session_date_and_integer_counts() -> None:
    raw = SimpleNamespace(
        timestamp=datetime(2024, 1, 6, 0, tzinfo=UTC),
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.5,
        volume=1000.0,
        vwap=10.2,
        trade_count=100.0,
    )
    adapter, _, _ = make_provider(FakeData({"AAPL": [raw]}))
    batch = list(adapter.get_daily_bars(["AAPL"], date(2024, 1, 5), date(2024, 1, 5), "sip"))[0]
    assert len(batch.bars) == 1
    assert batch.bars[0].date == date(2024, 1, 5)
    assert batch.bars[0].volume == 1000
    assert batch.bars[0].trade_count == 100


def test_one_bad_bar_yields_issue_but_good_bar_survives() -> None:
    good = SimpleNamespace(
        timestamp=datetime(2024, 1, 6, 0, tzinfo=UTC),
        open=10.0, high=11.0, low=9.0, close=10.5,
        volume=1000.0, vwap=10.2, trade_count=100.0,
    )
    bad = SimpleNamespace(**{**vars(good), "low": 12.0})
    adapter, _, _ = make_provider(FakeData({"AAPL": [good, bad]}))
    batch = list(adapter.get_daily_bars(["AAPL"], date(2024, 1, 5), date(2024, 1, 5), "sip"))[0]
    assert len(batch.bars) == 1
    assert len(batch.issues) == 1
    assert batch.issues[0].code == "invalid_provider_bar"


def test_zero_volume_zero_vwap_is_retained_as_missing_vwap() -> None:
    raw = SimpleNamespace(
        timestamp=datetime(2024, 1, 6, 0, tzinfo=UTC),
        open=10.0, high=10.0, low=10.0, close=10.0,
        volume=0.0, vwap=0.0, trade_count=0.0,
    )
    adapter, _, _ = make_provider(FakeData({"AAPL": [raw]}))
    batch = list(adapter.get_daily_bars(["AAPL"], date(2024, 1, 5), date(2024, 1, 5), "sip"))[0]
    assert len(batch.bars) == 1
    assert batch.bars[0].volume == 0
    assert batch.bars[0].vwap is None
    assert batch.issues == []


def test_positive_volume_zero_vwap_retains_ohlcv_with_warning() -> None:
    raw = SimpleNamespace(
        timestamp=datetime(2024, 1, 6, 0, tzinfo=UTC),
        open=10.0, high=11.0, low=9.0, close=10.5,
        volume=1000.0, vwap=0.0, trade_count=100.0,
    )
    adapter, _, _ = make_provider(FakeData({"AAPL": [raw]}))
    batch = list(adapter.get_daily_bars(["AAPL"], date(2024, 1, 5),
                                        date(2024, 1, 5), "sip"))[0]
    assert len(batch.bars) == 1
    assert batch.bars[0].close == 10.5
    assert batch.bars[0].vwap is None
    assert len(batch.issues) == 1
    assert batch.issues[0].code == "invalid_provider_vwap"
    assert batch.issues[0].date == date(2024, 1, 5)

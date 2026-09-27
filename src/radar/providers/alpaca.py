"""Official alpaca-py adapter for active US assets and daily stock bars."""

from __future__ import annotations

import logging
import math
import time
from collections.abc import Callable, Iterator, Sequence
from datetime import date, datetime, time as day_time, timezone
from typing import Any, TypeVar
from zoneinfo import ZoneInfo

from alpaca.common.exceptions import APIError
from alpaca.data.enums import Adjustment, DataFeed
from alpaca.data.historical import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import AssetClass, AssetStatus
from alpaca.trading.requests import GetAssetsRequest, GetCalendarRequest
from pydantic import ValidationError
from requests.exceptions import RequestException

from radar.models import (
    AssetRecord,
    DailyBar,
    ProviderBatchResult,
    ValidationIssue,
    normalize_symbol,
)

UTC = timezone.utc
NEW_YORK = ZoneInfo("America/New_York")
LOG = logging.getLogger(__name__)
T = TypeVar("T")


def _count(value: int | float | None) -> int | None:
    """alpaca-py types volumes as float even though bar counts are integral."""
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("bar count is not numeric")
    if not math.isfinite(value) or value < 0 or int(value) != value:
        raise ValueError("bar count must be a finite nonnegative integer")
    return int(value)


class ProviderError(RuntimeError):
    """A provider-wide failure that cannot be isolated to a few symbols."""


class _TimedTradingClient(TradingClient):
    def _one_request(self, method: str, url: str, opts: dict, retry: int) -> dict:
        return super()._one_request(method, url, {**opts, "timeout": (10, 30)}, retry)


class _TimedStockClient(StockHistoricalDataClient):
    def _one_request(self, method: str, url: str, opts: dict, retry: int) -> dict:
        return super()._one_request(method, url, {**opts, "timeout": (10, 60)}, retry)


class AlpacaProvider:
    """Batch stock bars; alpaca-py handles next_page_token within each batch.

    Failed symbols are isolated by splitting only a rejected batch. A broad
    request is never silently retried one ticker at a time in the normal path.
    """

    def __init__(
        self,
        trading_client: Any,
        data_client: Any,
        *,
        batch_size: int = 50,
        max_attempts: int = 5,
        sleep: Callable[[float], None] = time.sleep,
        now: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        if batch_size < 1 or max_attempts < 1:
            raise ValueError("batch_size and max_attempts must be positive")
        self.trading_client = trading_client
        self.data_client = data_client
        self.batch_size = batch_size
        self.max_attempts = max_attempts
        self.sleep = sleep
        self.now = now

    @classmethod
    def from_credentials(
        cls,
        api_key: str,
        secret_key: str,
        *,
        batch_size: int = 50,
        max_attempts: int = 5,
    ) -> AlpacaProvider:
        if not api_key or not secret_key:
            raise ValueError("Alpaca API key and secret key are required")
        return cls(
            _TimedTradingClient(api_key, secret_key, paper=True),
            _TimedStockClient(api_key, secret_key),
            batch_size=batch_size,
            max_attempts=max_attempts,
        )

    def _retry(self, operation: Callable[[], T]) -> T:
        for attempt in range(self.max_attempts):
            try:
                return operation()
            except APIError as error:
                status = getattr(error, "status_code", None)
                if status != 429 and not (isinstance(status, int) and 500 <= status < 600):
                    raise
            except (RequestException, TimeoutError):
                pass
            if attempt + 1 < self.max_attempts:
                # Cap the backoff at 30s so a long unattended batch download can
                # ride out a short provider/network hiccup instead of failing the
                # whole daily update after only a few seconds of retrying.
                self.sleep(min(2**attempt, 30))
        raise ProviderError(f"provider failed after {self.max_attempts} attempts")

    def get_assets(self) -> list[AssetRecord]:
        request = GetAssetsRequest(
            asset_class=AssetClass.US_EQUITY, status=AssetStatus.ACTIVE
        )
        raw_assets = self._retry(lambda: self.trading_client.get_all_assets(request))
        observed = self.now().astimezone(UTC)
        assets: list[AssetRecord] = []
        for raw in raw_assets:
            assets.append(
                AssetRecord(
                    symbol=raw.symbol,
                    name=raw.name,
                    exchange=raw.exchange.value if hasattr(raw.exchange, "value") else str(raw.exchange),
                    asset_class=raw.asset_class.value if hasattr(raw.asset_class, "value") else str(raw.asset_class),
                    status=raw.status.value if hasattr(raw.status, "value") else str(raw.status),
                    tradable=raw.tradable,
                    fractionable=raw.fractionable,
                    shortable=raw.shortable,
                    easy_to_borrow=raw.easy_to_borrow,
                    first_seen=observed,
                    last_seen=observed,
                    updated_at=observed,
                )
            )
        return assets

    def get_market_sessions(self, start: date, end: date) -> list[date]:
        if isinstance(start, datetime) or isinstance(end, datetime) or start > end:
            raise ValueError("start and end must be ordered market-session dates")
        calendar = self._retry(
            lambda: self.trading_client.get_calendar(GetCalendarRequest(start=start, end=end))
        )
        sessions = sorted({entry.date for entry in calendar})
        if any(day < start or day > end for day in sessions):
            raise ProviderError("Alpaca calendar returned an out-of-range date")
        return sessions

    def get_daily_bars(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
        feed: str,
        adjustment: str = "split",
    ) -> Iterator[ProviderBatchResult]:
        if isinstance(start, datetime) or isinstance(end, datetime) or start > end:
            raise ValueError("start and end must be ordered market-session dates")
        selected_feed = DataFeed(feed)
        selected_adjustment = Adjustment(adjustment)
        normalized = list(dict.fromkeys(normalize_symbol(symbol) for symbol in symbols))
        for offset in range(0, len(normalized), self.batch_size):
            batch = normalized[offset : offset + self.batch_size]
            bars, failures, issues = self._fetch_batch(
                batch, start, end, selected_feed, selected_adjustment
            )
            yield ProviderBatchResult(
                requested_symbols=batch,
                bars=bars,
                failed_symbols=failures,
                issues=issues,
                provider="alpaca",
                feed=selected_feed.value,
                start=start,
                end=end,
            )

    def _fetch_batch(
        self,
        symbols: list[str],
        start: date,
        end: date,
        feed: DataFeed,
        adjustment: Adjustment,
    ) -> tuple[list[DailyBar], dict[str, str], list[ValidationIssue]]:
        request = StockBarsRequest(
            symbol_or_symbols=symbols,
            timeframe=TimeFrame.Day,
            start=datetime.combine(start, day_time.min, NEW_YORK),
            end=datetime.combine(end, day_time.min, NEW_YORK),
            feed=feed,
            adjustment=adjustment,
        )
        try:
            response = self._retry(lambda: self.data_client.get_stock_bars(request))
        except APIError as error:
            status = getattr(error, "status_code", None)
            if status in {401, 403}:
                raise ProviderError(
                    f"Alpaca rejected credentials or access to feed {feed.value}"
                ) from error
            if status in {400, 404, 422} and len(symbols) > 1:
                midpoint = len(symbols) // 2
                left = self._fetch_batch(symbols[:midpoint], start, end, feed, adjustment)
                right = self._fetch_batch(symbols[midpoint:], start, end, feed, adjustment)
                return (
                    left[0] + right[0],
                    {**left[1], **right[1]},
                    left[2] + right[2],
                )
            reason = f"Alpaca HTTP {status or 'error'}"
            LOG.warning("Alpaca bar batch failed: %s", reason)
            return [], {symbol: reason for symbol in symbols}, []
        except ProviderError as error:
            return [], {symbol: str(error) for symbol in symbols}, []

        downloaded = self.now().astimezone(UTC)
        bars: list[DailyBar] = []
        issues: list[ValidationIssue] = []
        for symbol, raw_bars in response.data.items():
            for raw in raw_bars:
                try:
                    timestamp = raw.timestamp
                    if timestamp.tzinfo is None or timestamp.utcoffset() is None:
                        raise ValueError("provider bar timestamp is naive")
                    session = timestamp.astimezone(NEW_YORK).date()
                    if not start <= session <= end:
                        raise ValueError("provider bar session is outside requested range")
                    # With zero trades Alpaca can report VWAP=0. It is
                    # mathematically undefined, so store NULL rather than
                    # reject an otherwise valid zero-volume daily bar.
                    vwap = None if raw.volume == 0 and raw.vwap == 0 else raw.vwap
                    bars.append(
                        DailyBar(
                            symbol=symbol,
                            date=session,
                            open=raw.open,
                            high=raw.high,
                            low=raw.low,
                            close=raw.close,
                            volume=_count(raw.volume),
                            vwap=vwap,
                            trade_count=_count(raw.trade_count),
                            provider="alpaca",
                            feed=feed.value,
                            adjustment=adjustment.value,
                            downloaded_at=downloaded,
                        )
                    )
                except (ValidationError, ValueError, TypeError, AttributeError) as error:
                    issues.append(
                        ValidationIssue(
                            code="invalid_provider_bar",
                            message=str(error),
                            severity="error",
                            symbol=symbol,
                        )
                    )
        return bars, {}, issues

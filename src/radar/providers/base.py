"""Provider contract for Phase 1 asset and daily-bar ingestion."""

from __future__ import annotations

from collections.abc import Iterator, Sequence
from datetime import date
from typing import Protocol

from radar.models import AssetRecord, ProviderBatchResult


class MarketDataProvider(Protocol):
    def get_assets(self) -> list[AssetRecord]:
        """Return the active US-equity asset master."""

    def get_market_sessions(self, start: date, end: date) -> list[date]:
        """Return exchange session dates in an inclusive range."""

    def get_daily_bars(
        self,
        symbols: Sequence[str],
        start: date,
        end: date,
        feed: str,
        adjustment: str = "split",
    ) -> Iterator[ProviderBatchResult]:
        """Yield batches over inclusive New York market-session dates."""

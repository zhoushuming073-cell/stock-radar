"""Phase 1B core models for the stock-radar data foundation.

Shared conventions for every model in this module:

* datetimes are timezone-aware and normalized to UTC; naive input is rejected;
* ``date`` fields are US/Eastern market session dates supplied by the caller
  after converting the provider timestamp to America/New_York. A session date is
  never derived from a UTC timestamp inside these models;
* symbols are trimmed and uppercased, and may contain ``.`` or ``-``.

These models are pure data contracts: no network and no database code.
"""

from __future__ import annotations

import math
import re
from datetime import date as date_cls
from datetime import datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

UTC = timezone.utc

# Letters/digits, optionally joined by a single '.' or '-' (e.g. BRK.B, RDS-A).
_SYMBOL_PATTERN = re.compile(r"^[A-Z0-9]+(?:[.\-][A-Z0-9]+)*$")


def normalize_symbol(value: Any) -> str:
    """Trim + uppercase a symbol and reject anything that is not symbol-shaped."""
    if not isinstance(value, str):
        raise ValueError("symbol must be a string")
    symbol = value.strip().upper()
    if not _SYMBOL_PATTERN.fullmatch(symbol):
        raise ValueError(
            "symbol must be a nonempty symbol built from letters/digits, "
            "optionally joined by '.' or '-'"
        )
    return symbol


def _to_utc(value: datetime) -> datetime:
    """Reject naive datetimes and normalize aware ones to UTC."""
    if value.tzinfo is None or value.tzinfo.utcoffset(value) is None:
        raise ValueError("datetime must be timezone-aware")
    return value.astimezone(UTC)


def _finite_price(value: float) -> float:
    if not math.isfinite(value):
        raise ValueError("price must be a finite number")
    return value


def _session_date(value: Any) -> Any:
    if isinstance(value, datetime):
        raise ValueError(
            "session date must be a datetime.date; convert the provider "
            "timestamp to America/New_York in the caller and pass that date"
        )
    return value


def _normalize_failed_symbols(value: Any) -> Any:
    """Normalize failure-map keys to symbols and require nonempty reasons."""
    if not isinstance(value, dict):
        return value
    normalized: dict[str, str] = {}
    for raw_symbol, reason in value.items():
        symbol = normalize_symbol(raw_symbol)
        if not isinstance(reason, str) or not reason.strip():
            raise ValueError(
                f"failure reason for {symbol!r} must be a nonempty string"
            )
        normalized[symbol] = reason.strip()
    return normalized


Symbol = Annotated[str, BeforeValidator(normalize_symbol)]
UtcDatetime = Annotated[datetime, AfterValidator(_to_utc)]
SessionDate = Annotated[date_cls, BeforeValidator(_session_date)]
PositivePrice = Annotated[float, Field(gt=0), AfterValidator(_finite_price)]
NonNegativeInt = Annotated[int, Field(ge=0, strict=True)]
NonEmptyText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
FailureReasons = Annotated[dict[str, str], BeforeValidator(_normalize_failed_symbols)]


class RadarModel(BaseModel):
    """Base config: unknown fields are corruption, assignments stay validated."""

    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class AssetRecord(RadarModel):
    """One row of the asset master (`assets` table)."""

    symbol: Symbol
    name: str | None = None
    exchange: str | None = None
    asset_class: NonEmptyText
    status: NonEmptyText

    tradable: bool
    fractionable: bool
    shortable: bool
    easy_to_borrow: bool

    # First time this asset was observed in the provider asset master.
    first_seen: UtcDatetime
    # Most recent time this asset was observed in the provider asset master.
    last_seen: UtcDatetime
    # Most recent time the local database row was written.
    updated_at: UtcDatetime

    @model_validator(mode="after")
    def _check_observation_order(self) -> AssetRecord:
        if self.first_seen > self.last_seen:
            raise ValueError("first_seen must be <= last_seen")
        if self.last_seen > self.updated_at:
            raise ValueError("last_seen must be <= updated_at")
        return self


class DailyBar(RadarModel):
    """One daily OHLCV bar (`daily_bars` table)."""

    symbol: Symbol
    # US/Eastern market session date, supplied by the caller.
    date: SessionDate

    open: PositivePrice
    high: PositivePrice
    low: PositivePrice
    close: PositivePrice
    volume: NonNegativeInt
    vwap: PositivePrice | None = None
    trade_count: NonNegativeInt | None = None

    provider: NonEmptyText
    feed: NonEmptyText
    adjustment: NonEmptyText
    timeframe: Literal["1Day"] = "1Day"
    # UTC retrieval time of this bar from the provider.
    downloaded_at: UtcDatetime

    @model_validator(mode="after")
    def _check_ohlc(self) -> DailyBar:
        if self.high < self.low:
            raise ValueError("high must be >= low")
        if self.high < self.open:
            raise ValueError("high must be >= open")
        if self.high < self.close:
            raise ValueError("high must be >= close")
        if self.low > self.open:
            raise ValueError("low must be <= open")
        if self.low > self.close:
            raise ValueError("low must be <= close")
        return self


class ValidationIssue(RadarModel):
    """A single structured data-quality problem found during a run."""

    code: NonEmptyText
    message: NonEmptyText
    severity: Literal["warning", "error"]
    symbol: Symbol | None = None
    date: SessionDate | None = None
    details: dict[str, Any] = Field(default_factory=dict)


class ValidationSummary(RadarModel):
    """Structured result of validating a collection of daily bars."""

    checked_rows: NonNegativeInt
    accepted_rows: NonNegativeInt
    rejected_rows: NonNegativeInt
    issues: list[ValidationIssue] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_totals(self) -> ValidationSummary:
        if self.accepted_rows + self.rejected_rows != self.checked_rows:
            raise ValueError("accepted_rows + rejected_rows must equal checked_rows")
        return self


class ProviderBatchResult(RadarModel):
    """Result of one provider request batch. partial success is valid."""

    requested_symbols: list[Symbol]
    bars: list[DailyBar] = Field(default_factory=list)
    failed_symbols: FailureReasons = Field(default_factory=dict)
    issues: list[ValidationIssue] = Field(default_factory=list)
    provider: NonEmptyText
    feed: NonEmptyText
    # Market session dates covered by the request, inclusive.
    start: SessionDate
    end: SessionDate

    @field_validator("requested_symbols", mode="after")
    @classmethod
    def _dedupe_symbols(cls, value: list[str]) -> list[str]:
        unique: list[str] = []
        seen: set[str] = set()
        for symbol in value:
            if symbol not in seen:
                seen.add(symbol)
                unique.append(symbol)
        return unique

    @model_validator(mode="after")
    def _check_date_range(self) -> ProviderBatchResult:
        if self.start > self.end:
            raise ValueError("start must be <= end")
        return self


class IngestionResult(RadarModel):
    """Run summary of one ingestion job. Not database code."""

    fetched_rows: NonNegativeInt
    inserted_rows: NonNegativeInt
    updated_rows: NonNegativeInt
    unchanged_rows: NonNegativeInt
    rejected_rows: NonNegativeInt
    batch_count: NonNegativeInt
    issues: list[ValidationIssue] = Field(default_factory=list)
    failed_symbols: FailureReasons = Field(default_factory=dict)

    @model_validator(mode="after")
    def _check_row_accounting(self) -> IngestionResult:
        accounted = (
            self.inserted_rows
            + self.updated_rows
            + self.unchanged_rows
            + self.rejected_rows
        )
        if accounted > self.fetched_rows:
            raise ValueError(
                "inserted + updated + unchanged + rejected rows "
                f"({accounted}) must be <= fetched_rows ({self.fetched_rows})"
            )
        return self

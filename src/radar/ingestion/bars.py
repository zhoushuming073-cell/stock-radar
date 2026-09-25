"""Trading-session-aware, restartable daily-bar ingestion."""

from __future__ import annotations

import logging
from collections import defaultdict
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import date, datetime

import duckdb

from radar.db import WriteStats, upsert_daily_bars
from radar.models import DailyBar, IngestionResult, ValidationIssue, normalize_symbol
from radar.providers.base import MarketDataProvider
from radar.validation.bars import validate_daily_bars

LOG = logging.getLogger(__name__)


@dataclass(frozen=True)
class DownloadWindow:
    start: date
    end: date
    symbols: tuple[str, ...]


def _chunks(items: Sequence[str], size: int) -> Iterable[Sequence[str]]:
    for offset in range(0, len(items), size):
        yield items[offset : offset + size]


def plan_missing_windows(
    connection: duckdb.DuckDBPyConnection,
    symbols: Sequence[str],
    sessions: Sequence[date],
) -> list[DownloadWindow]:
    """Group consecutive missing sessions, then batch symbols by equal window."""
    ordered_sessions = sorted(set(sessions))
    if any(isinstance(day, datetime) for day in ordered_sessions):
        raise ValueError("sessions must be dates, not datetimes")
    if not ordered_sessions:
        return []
    normalized = list(dict.fromkeys(normalize_symbol(symbol) for symbol in symbols))
    windows: dict[tuple[date, date], list[str]] = defaultdict(list)
    for chunk in _chunks(normalized, 500):
        placeholders = ",".join("?" for _ in chunk)
        stored = connection.execute(
            f"""SELECT symbol, date FROM daily_bars
                WHERE symbol IN ({placeholders}) AND date BETWEEN ? AND ?""",
            [*chunk, ordered_sessions[0], ordered_sessions[-1]],
        ).fetchall()
        present: dict[str, set[date]] = defaultdict(set)
        for symbol, day in stored:
            present[symbol].add(day)
        for symbol in chunk:
            first: date | None = None
            last: date | None = None
            for day in ordered_sessions:
                if day not in present[symbol]:
                    first = day if first is None else first
                    last = day
                elif first is not None and last is not None:
                    windows[(first, last)].append(symbol)
                    first = last = None
            if first is not None and last is not None:
                windows[(first, last)].append(symbol)
    return [
        DownloadWindow(start, end, tuple(sorted(batch)))
        for (start, end), batch in sorted(windows.items())
    ]


def _check_existing_provenance(
    connection: duckdb.DuckDBPyConnection,
    symbols: Sequence[str],
    sessions: Sequence[date],
    provider_name: str,
    feed: str,
    adjustment: str,
) -> None:
    if not symbols or not sessions:
        return
    for chunk in _chunks(symbols, 500):
        placeholders = ",".join("?" for _ in chunk)
        count = connection.execute(
            f"""SELECT COUNT(*) FROM daily_bars
                WHERE symbol IN ({placeholders}) AND date BETWEEN ? AND ?
                  AND (provider IS DISTINCT FROM ? OR feed IS DISTINCT FROM ?
                       OR adjustment IS DISTINCT FROM ?)""",
            [*chunk, min(sessions), max(sessions), provider_name, feed, adjustment],
        ).fetchone()[0]
        if count:
            raise ValueError(
                f"{count} stored bars use a different provider/feed/adjustment"
            )


def _write_with_isolation(
    connection: duckdb.DuckDBPyConnection,
    bars: list[DailyBar],
    failed_symbols: dict[str, str],
    issues: list[ValidationIssue],
) -> tuple[WriteStats, int]:
    if not bars:
        return WriteStats(), 0
    try:
        return upsert_daily_bars(connection, bars), 0
    except ValueError:
        # A provenance or equal-time conflict can affect one ticker only.
        # Retrying small symbol subsets preserves the rest of the batch.
        grouped: dict[str, list[DailyBar]] = defaultdict(list)
        for bar in bars:
            grouped[bar.symbol].append(bar)
        total = WriteStats()
        rejected = 0
        for symbol, subset in grouped.items():
            try:
                result = upsert_daily_bars(connection, subset)
                total = WriteStats(
                    total.inserted + result.inserted,
                    total.updated + result.updated,
                    total.unchanged + result.unchanged,
                )
            except ValueError as error:
                failed_symbols[symbol] = str(error)
                rejected += len(subset)
                issues.append(
                    ValidationIssue(
                        code="database_bar_conflict",
                        message=str(error),
                        severity="error",
                        symbol=symbol,
                    )
                )
                LOG.warning("Bar write rejected for %s: %s", symbol, error)
        return total, rejected


def ingest_daily_bars(
    connection: duckdb.DuckDBPyConnection,
    provider: MarketDataProvider,
    symbols: Sequence[str],
    sessions: Sequence[date],
    *,
    feed: str,
    adjustment: str = "split",
    provider_name: str = "alpaca",
) -> IngestionResult:
    """Download only currently missing trading-session windows and persist them."""
    normalized = list(dict.fromkeys(normalize_symbol(symbol) for symbol in symbols))
    _check_existing_provenance(
        connection, normalized, sessions, provider_name, feed, adjustment
    )
    windows = plan_missing_windows(connection, normalized, sessions)
    fetched = rejected = batch_count = 0
    written = WriteStats()
    issues: list[ValidationIssue] = []
    failures: dict[str, str] = {}
    for window in windows:
        for batch in provider.get_daily_bars(
            window.symbols, window.start, window.end, feed, adjustment
        ):
            if batch.provider != provider_name or batch.feed != feed:
                raise ValueError("provider batch provenance differs from requested source")
            if any(
                bar.provider != provider_name or bar.feed != feed or bar.adjustment != adjustment
                for bar in batch.bars
            ):
                raise ValueError("provider bar provenance differs from requested source")
            batch_count += 1
            issues.extend(batch.issues)
            invalid_count = sum(issue.code == "invalid_provider_bar" for issue in batch.issues)
            fetched += len(batch.bars) + invalid_count
            rejected += invalid_count
            for symbol, reason in batch.failed_symbols.items():
                failures[symbol] = reason
                LOG.warning("Bar download failed for %s: %s", symbol, reason)
            unique, validation = validate_daily_bars(batch.bars)
            issues.extend(validation.issues)
            rejected += validation.rejected_rows
            stats, rejected_by_db = _write_with_isolation(
                connection, unique, failures, issues
            )
            rejected += rejected_by_db
            written = WriteStats(
                written.inserted + stats.inserted,
                written.updated + stats.updated,
                written.unchanged + stats.unchanged,
            )
            if batch_count % 10 == 0:
                LOG.info(
                    "processed %d provider batches; inserted=%d rejected=%d failed_symbols=%d",
                    batch_count, written.inserted, rejected, len(failures),
                )
    return IngestionResult(
        fetched_rows=fetched,
        inserted_rows=written.inserted,
        updated_rows=written.updated,
        unchanged_rows=written.unchanged,
        rejected_rows=rejected,
        batch_count=batch_count,
        issues=issues,
        failed_symbols=failures,
    )

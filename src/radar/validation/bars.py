"""Daily-bar validity checks and non-destructive research warnings."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence
from datetime import date
from typing import Any

import duckdb
from pydantic import ValidationError

from radar.models import (
    DailyBar,
    ValidationIssue,
    ValidationSummary,
    normalize_symbol,
)


def _optional_symbol(row: Any) -> str | None:
    raw = row.get("symbol") if isinstance(row, Mapping) else getattr(row, "symbol", None)
    try:
        return normalize_symbol(raw)
    except (TypeError, ValueError):
        return None


def validate_daily_bars(
    rows: Iterable[DailyBar | Mapping[str, Any]],
    *,
    expected_sessions: Sequence[date] = (),
    jump_fraction: float = 0.5,
    stale_after_sessions: int = 5,
) -> tuple[list[DailyBar], ValidationSummary]:
    """Reject malformed/duplicate rows and flag gaps or jumps for review.

    Large jumps remain in the accepted set because splits and other corporate
    actions can produce them. Session coverage is checked only between a
    symbol's first and last bar; prior sessions may predate its listing.
    """
    if jump_fraction <= 0 or stale_after_sessions < 1:
        raise ValueError("jump_fraction and stale_after_sessions must be positive")
    issues: list[ValidationIssue] = []
    valid: dict[tuple[str, date], DailyBar] = {}
    checked = 0
    rejected = 0
    for row in rows:
        checked += 1
        try:
            bar = row if isinstance(row, DailyBar) else DailyBar.model_validate(row)
        except ValidationError as error:
            rejected += 1
            kind = "missing_field" if any(
                issue["type"] == "missing" for issue in error.errors()
            ) else "invalid_bar"
            issues.append(
                ValidationIssue(
                    code=kind,
                    message=str(error),
                    severity="error",
                    symbol=_optional_symbol(row),
                )
            )
            continue
        key = (bar.symbol, bar.date)
        if key in valid:
            rejected += 1
            issues.append(
                ValidationIssue(
                    code="duplicate_symbol_date",
                    message="duplicate daily bar for symbol and session date",
                    severity="error",
                    symbol=bar.symbol,
                    date=bar.date,
                )
            )
            continue
        valid[key] = bar
    bars = sorted(valid.values(), key=lambda bar: (bar.symbol, bar.date))
    by_symbol: dict[str, list[DailyBar]] = defaultdict(list)
    for bar in bars:
        by_symbol[bar.symbol].append(bar)
    sessions = sorted(set(expected_sessions))
    for symbol, series in by_symbol.items():
        previous: DailyBar | None = None
        for bar in series:
            if previous is not None:
                change = bar.close / previous.close - 1
                if abs(change) > jump_fraction:
                    issues.append(
                        ValidationIssue(
                            code="abnormal_price_jump",
                            message="large close-to-close change requires corporate-action review",
                            severity="warning",
                            symbol=symbol,
                            date=bar.date,
                            details={"fraction": change, "previous_date": previous.date.isoformat()},
                        )
                    )
            previous = bar
        if sessions:
            available = {bar.date for bar in series}
            for session in sessions:
                if series[0].date < session < series[-1].date and session not in available:
                    issues.append(
                        ValidationIssue(
                            code="missing_trading_session",
                            message="no bar for an intervening market session",
                            severity="warning",
                            symbol=symbol,
                            date=session,
                        )
                    )
            trailing = sum(day > series[-1].date for day in sessions)
            if trailing >= stale_after_sessions:
                issues.append(
                    ValidationIssue(
                        code="stale_ticker",
                        message=f"no bar for {trailing} recent market sessions",
                        severity="warning",
                        symbol=symbol,
                        date=series[-1].date,
                    )
                )
    return bars, ValidationSummary(
        checked_rows=checked,
        accepted_rows=len(bars),
        rejected_rows=rejected,
        issues=issues,
    )


def validate_database(
    connection: duckdb.DuckDBPyConnection,
    symbols: Sequence[str],
    sessions: Sequence[date],
) -> ValidationSummary:
    """Validate persisted bars in bounded symbol chunks without loading all rows."""
    if not sessions:
        return ValidationSummary(checked_rows=0, accepted_rows=0, rejected_rows=0)
    issues: list[ValidationIssue] = []
    checked = accepted = rejected = 0
    names = (
        "symbol", "date", "open", "high", "low", "close", "volume", "vwap",
        "trade_count", "provider", "feed", "adjustment", "downloaded_at",
    )
    for offset in range(0, len(symbols), 100):
        batch = symbols[offset : offset + 100]
        if not batch:
            continue
        placeholders = ",".join("?" for _ in batch)
        data = connection.execute(
            f"""SELECT {', '.join(names)} FROM daily_bars
                WHERE symbol IN ({placeholders}) AND date BETWEEN ? AND ?""",
            [*batch, min(sessions), max(sessions)],
        ).fetchall()
        rows = [dict(zip(names, values)) for values in data]
        valid, summary = validate_daily_bars(rows, expected_sessions=sessions)
        checked += summary.checked_rows
        accepted += summary.accepted_rows
        rejected += summary.rejected_rows
        issues.extend(summary.issues)
        present = {bar.symbol for bar in valid}
        for symbol in batch:
            if symbol not in present:
                issues.append(
                    ValidationIssue(
                        code="no_bars",
                        message="no stored bars in requested session window",
                        severity="warning",
                        symbol=symbol,
                    )
                )
    return ValidationSummary(
        checked_rows=checked,
        accepted_rows=accepted,
        rejected_rows=rejected,
        issues=issues,
    )

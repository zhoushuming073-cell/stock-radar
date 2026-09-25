"""DuckDB connection and atomic, idempotent daily-bar writes."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from uuid import uuid4

import duckdb
import pyarrow as pa

from radar.models import AssetRecord, DailyBar
from radar.schema import ensure_schema


@dataclass(frozen=True)
class WriteStats:
    inserted: int = 0
    updated: int = 0
    unchanged: int = 0


def get_connection(path: str | Path) -> duckdb.DuckDBPyConnection:
    """Open a caller-owned connection, creating a file database if needed."""
    location = str(path)
    if location != ":memory:":
        Path(location).parent.mkdir(parents=True, exist_ok=True)
    connection = duckdb.connect(location)
    try:
        ensure_schema(connection)
    except Exception:
        connection.close()
        raise
    return connection


_BAR_ARROW_SCHEMA = pa.schema(
    [
        ("symbol", pa.string()),
        ("date", pa.date32()),
        ("open", pa.float64()),
        ("high", pa.float64()),
        ("low", pa.float64()),
        ("close", pa.float64()),
        ("volume", pa.int64()),
        ("vwap", pa.float64()),
        ("trade_count", pa.int64()),
        ("provider", pa.string()),
        ("feed", pa.string()),
        ("adjustment", pa.string()),
        ("downloaded_at", pa.timestamp("us", tz="UTC")),
    ]
)

_ASSET_ARROW_SCHEMA = pa.schema(
    [
        ("symbol", pa.string()),
        ("name", pa.string()),
        ("exchange", pa.string()),
        ("asset_class", pa.string()),
        ("status", pa.string()),
        ("tradable", pa.bool_()),
        ("fractionable", pa.bool_()),
        ("shortable", pa.bool_()),
        ("easy_to_borrow", pa.bool_()),
        ("first_seen", pa.timestamp("us", tz="UTC")),
        ("last_seen", pa.timestamp("us", tz="UTC")),
        ("updated_at", pa.timestamp("us", tz="UTC")),
    ]
)


def upsert_assets(
    connection: duckdb.DuckDBPyConnection, assets: Iterable[AssetRecord]
) -> WriteStats:
    """Bulk upsert the asset master without letting stale snapshots win."""
    records = [asset.model_dump() for asset in assets]
    if not records:
        return WriteStats()
    symbols = [record["symbol"] for record in records]
    if len(symbols) != len(set(symbols)):
        raise ValueError("incoming asset batch contains duplicate symbols")
    arrow = pa.Table.from_pylist(records, schema=_ASSET_ARROW_SCHEMA)
    view = f"incoming_assets_{uuid4().hex}"
    connection.register(view, arrow)
    fresh = """(
        incoming.last_seen > stored.last_seen OR
        (incoming.last_seen = stored.last_seen AND
         incoming.updated_at > stored.updated_at)
    )"""
    try:
        connection.execute("BEGIN TRANSACTION")
        try:
            inserted, updated, unchanged = connection.execute(
                f"""
                SELECT
                    COUNT(*) FILTER (WHERE stored.symbol IS NULL),
                    COUNT(*) FILTER (
                        WHERE stored.symbol IS NOT NULL AND
                        (incoming.first_seen < stored.first_seen OR {fresh})
                    ),
                    COUNT(*) FILTER (
                        WHERE stored.symbol IS NOT NULL AND NOT
                        (incoming.first_seen < stored.first_seen OR {fresh})
                    )
                FROM {view} AS incoming
                LEFT JOIN assets AS stored USING (symbol)
                """
            ).fetchone()
            connection.execute(
                f"""
                INSERT INTO assets SELECT * FROM {view}
                ON CONFLICT (symbol) DO UPDATE SET
                    first_seen = LEAST(assets.first_seen, excluded.first_seen),
                    last_seen = GREATEST(assets.last_seen, excluded.last_seen),
                    updated_at = GREATEST(assets.updated_at, excluded.updated_at),
                    name = CASE WHEN
                        excluded.last_seen > assets.last_seen OR
                        (excluded.last_seen = assets.last_seen AND
                         excluded.updated_at > assets.updated_at)
                        THEN excluded.name ELSE assets.name END,
                    exchange = CASE WHEN
                        excluded.last_seen > assets.last_seen OR
                        (excluded.last_seen = assets.last_seen AND
                         excluded.updated_at > assets.updated_at)
                        THEN excluded.exchange ELSE assets.exchange END,
                    asset_class = CASE WHEN
                        excluded.last_seen > assets.last_seen OR
                        (excluded.last_seen = assets.last_seen AND
                         excluded.updated_at > assets.updated_at)
                        THEN excluded.asset_class ELSE assets.asset_class END,
                    status = CASE WHEN
                        excluded.last_seen > assets.last_seen OR
                        (excluded.last_seen = assets.last_seen AND
                         excluded.updated_at > assets.updated_at)
                        THEN excluded.status ELSE assets.status END,
                    tradable = CASE WHEN
                        excluded.last_seen > assets.last_seen OR
                        (excluded.last_seen = assets.last_seen AND
                         excluded.updated_at > assets.updated_at)
                        THEN excluded.tradable ELSE assets.tradable END,
                    fractionable = CASE WHEN
                        excluded.last_seen > assets.last_seen OR
                        (excluded.last_seen = assets.last_seen AND
                         excluded.updated_at > assets.updated_at)
                        THEN excluded.fractionable ELSE assets.fractionable END,
                    shortable = CASE WHEN
                        excluded.last_seen > assets.last_seen OR
                        (excluded.last_seen = assets.last_seen AND
                         excluded.updated_at > assets.updated_at)
                        THEN excluded.shortable ELSE assets.shortable END,
                    easy_to_borrow = CASE WHEN
                        excluded.last_seen > assets.last_seen OR
                        (excluded.last_seen = assets.last_seen AND
                         excluded.updated_at > assets.updated_at)
                        THEN excluded.easy_to_borrow ELSE assets.easy_to_borrow END
                WHERE excluded.first_seen < assets.first_seen OR
                      excluded.last_seen > assets.last_seen OR
                      (excluded.last_seen = assets.last_seen AND
                       excluded.updated_at > assets.updated_at)
                """
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
    finally:
        connection.unregister(view)
    return WriteStats(inserted, updated, unchanged)


def upsert_daily_bars(
    connection: duckdb.DuckDBPyConnection, bars: Iterable[DailyBar]
) -> WriteStats:
    """Bulk write bars; newer downloads replace only identical-provenance rows.

    A same-time revision or a change in provider/feed/adjustment is rejected.
    This prevents a rerun from silently changing the meaning of a price series.
    The whole supplied batch succeeds or fails in one transaction.
    """
    records = [bar.model_dump(exclude={"timeframe"}) for bar in bars]
    if not records:
        return WriteStats()
    keys = [(row["symbol"], row["date"]) for row in records]
    if len(keys) != len(set(keys)):
        raise ValueError("incoming daily bars contain duplicate (symbol, date) keys")
    arrow = pa.Table.from_pylist(records, schema=_BAR_ARROW_SCHEMA)
    view = f"incoming_bars_{uuid4().hex}"
    connection.register(view, arrow)
    try:
        connection.execute("BEGIN TRANSACTION")
        try:
            provenance_conflicts = connection.execute(
                f"""
                SELECT COUNT(*) FROM {view} AS incoming
                JOIN daily_bars AS stored USING (symbol, date)
                WHERE incoming.provider IS DISTINCT FROM stored.provider
                   OR incoming.feed IS DISTINCT FROM stored.feed
                   OR incoming.adjustment IS DISTINCT FROM stored.adjustment
                """
            ).fetchone()[0]
            if provenance_conflicts:
                raise ValueError(
                    f"{provenance_conflicts} existing daily bars have different provenance"
                )
            same_time_conflicts = connection.execute(
                f"""
                SELECT COUNT(*) FROM {view} AS incoming
                JOIN daily_bars AS stored USING (symbol, date)
                WHERE incoming.downloaded_at = stored.downloaded_at
                  AND (
                      incoming.open IS DISTINCT FROM stored.open OR
                      incoming.high IS DISTINCT FROM stored.high OR
                      incoming.low IS DISTINCT FROM stored.low OR
                      incoming.close IS DISTINCT FROM stored.close OR
                      incoming.volume IS DISTINCT FROM stored.volume OR
                      incoming.vwap IS DISTINCT FROM stored.vwap OR
                      incoming.trade_count IS DISTINCT FROM stored.trade_count
                  )
                """
            ).fetchone()[0]
            if same_time_conflicts:
                raise ValueError(
                    f"{same_time_conflicts} daily bars changed at the same download time"
                )
            inserted, updated, unchanged = connection.execute(
                f"""
                SELECT
                    COUNT(*) FILTER (WHERE stored.symbol IS NULL),
                    COUNT(*) FILTER (
                        WHERE stored.symbol IS NOT NULL
                          AND incoming.downloaded_at > stored.downloaded_at
                    ),
                    COUNT(*) FILTER (
                        WHERE stored.symbol IS NOT NULL
                          AND incoming.downloaded_at <= stored.downloaded_at
                    )
                FROM {view} AS incoming
                LEFT JOIN daily_bars AS stored USING (symbol, date)
                """
            ).fetchone()
            connection.execute(
                f"""
                INSERT INTO daily_bars
                SELECT symbol, date, open, high, low, close, volume, vwap,
                       trade_count, provider, feed, adjustment, downloaded_at
                FROM {view}
                ON CONFLICT (symbol, date) DO UPDATE SET
                    open = excluded.open,
                    high = excluded.high,
                    low = excluded.low,
                    close = excluded.close,
                    volume = excluded.volume,
                    vwap = excluded.vwap,
                    trade_count = excluded.trade_count,
                    downloaded_at = excluded.downloaded_at
                WHERE excluded.downloaded_at > daily_bars.downloaded_at
                """
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
    finally:
        connection.unregister(view)
    return WriteStats(inserted, updated, unchanged)

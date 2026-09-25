"""DuckDB schema for the Phase 1 data foundation.

All timestamps are UTC instants stored as TIMESTAMPTZ. Future db.py upserts
should retain an asset's earliest first_seen and latest last_seen, and accept
mutable attributes only from an equal or newer observation. A daily bar may be
replaced only by a newer download with the same provider, feed and adjustment;
a provenance mismatch must raise an error rather than silently mixing series.
"""

from __future__ import annotations

import duckdb

SCHEMA_VERSION = 1

EXPECTED_COLUMNS = {
    "assets": {
        "symbol": "VARCHAR",
        "name": "VARCHAR",
        "exchange": "VARCHAR",
        "asset_class": "VARCHAR",
        "status": "VARCHAR",
        "tradable": "BOOLEAN",
        "fractionable": "BOOLEAN",
        "shortable": "BOOLEAN",
        "easy_to_borrow": "BOOLEAN",
        "first_seen": "TIMESTAMP WITH TIME ZONE",
        "last_seen": "TIMESTAMP WITH TIME ZONE",
        "updated_at": "TIMESTAMP WITH TIME ZONE",
    },
    "daily_bars": {
        "symbol": "VARCHAR",
        "date": "DATE",
        "open": "DOUBLE",
        "high": "DOUBLE",
        "low": "DOUBLE",
        "close": "DOUBLE",
        "volume": "BIGINT",
        "vwap": "DOUBLE",
        "trade_count": "BIGINT",
        "provider": "VARCHAR",
        "feed": "VARCHAR",
        "adjustment": "VARCHAR",
        "downloaded_at": "TIMESTAMP WITH TIME ZONE",
    },
}


def _check_existing_columns(connection: duckdb.DuckDBPyConnection, table: str) -> None:
    rows = connection.execute(f"PRAGMA table_info('{table}')").fetchall()
    actual = {row[1]: row[2] for row in rows}
    expected = EXPECTED_COLUMNS[table]
    mismatches = {
        name: (kind, actual.get(name))
        for name, kind in expected.items()
        if actual.get(name) != kind
    }
    if mismatches:
        raise ValueError(f"{table} has missing or incompatible columns: {mismatches}")
    primary_key = {row[1] for row in rows if row[5]}
    required_key = {"symbol"} if table == "assets" else {"symbol", "date"}
    if primary_key != required_key:
        raise ValueError(f"{table} has incompatible primary key: {primary_key}")


def ensure_schema(connection: duckdb.DuckDBPyConnection) -> None:
    """Create version 1 atomically; repeated calls preserve existing rows."""
    connection.execute("BEGIN TRANSACTION")
    try:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS assets (
                symbol VARCHAR PRIMARY KEY,
                name VARCHAR, exchange VARCHAR, asset_class VARCHAR,
                status VARCHAR, tradable BOOLEAN, fractionable BOOLEAN,
                shortable BOOLEAN, easy_to_borrow BOOLEAN,
                first_seen TIMESTAMPTZ, last_seen TIMESTAMPTZ,
                updated_at TIMESTAMPTZ
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_bars (
                symbol VARCHAR, date DATE,
                open DOUBLE, high DOUBLE, low DOUBLE, close DOUBLE,
                volume BIGINT, vwap DOUBLE, trade_count BIGINT,
                provider VARCHAR, feed VARCHAR, adjustment VARCHAR,
                downloaded_at TIMESTAMPTZ,
                PRIMARY KEY (symbol, date)
            )
            """
        )
        for table in EXPECTED_COLUMNS:
            _check_existing_columns(connection, table)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO schema_migrations VALUES (?, current_timestamp) ON CONFLICT DO NOTHING",
            [SCHEMA_VERSION],
        )
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise

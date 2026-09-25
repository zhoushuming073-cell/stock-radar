"""Schema creation and migration safety checks."""

from __future__ import annotations

import duckdb
import pytest

from radar.schema import EXPECTED_COLUMNS, ensure_schema


def test_expected_columns_and_bar_key() -> None:
    connection = duckdb.connect(":memory:")
    ensure_schema(connection)
    for table, expected in EXPECTED_COLUMNS.items():
        actual = {
            row[1]: row[2]
            for row in connection.execute(f"PRAGMA table_info('{table}')").fetchall()
        }
        assert all(actual.get(name) == kind for name, kind in expected.items())

    connection.execute("INSERT INTO daily_bars (symbol, date) VALUES ('AAPL', '2024-01-05')")
    with pytest.raises(duckdb.ConstraintException):
        connection.execute("INSERT INTO daily_bars (symbol, date) VALUES ('AAPL', '2024-01-05')")


def test_repeat_creation_preserves_data_and_single_version() -> None:
    connection = duckdb.connect(":memory:")
    ensure_schema(connection)
    connection.execute("INSERT INTO assets (symbol) VALUES ('AAPL')")
    ensure_schema(connection)
    assert connection.execute("SELECT symbol FROM assets").fetchall() == [("AAPL",)]
    assert connection.execute("SELECT version FROM schema_migrations").fetchall() == [(1,)]


def test_incompatible_existing_table_rolls_back() -> None:
    connection = duckdb.connect(":memory:")
    connection.execute("CREATE TABLE assets (symbol VARCHAR PRIMARY KEY)")
    with pytest.raises(ValueError, match="incompatible columns"):
        ensure_schema(connection)
    assert connection.execute(
        "SELECT count(*) FROM information_schema.tables WHERE table_name = 'daily_bars'"
    ).fetchone()[0] == 0

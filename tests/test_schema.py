"""Schema creation and migration safety checks."""

from __future__ import annotations

from datetime import date

import duckdb
import pytest

from radar.schema import (EXPECTED_COLUMNS, RESEARCH_COLUMNS, STRATEGY2_EXTRA_COLUMNS,
                          ensure_research_schema, ensure_schema)


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


def test_research_migration_is_idempotent_and_preserves_raw_bars() -> None:
    connection = duckdb.connect(":memory:")
    ensure_schema(connection)
    connection.execute("INSERT INTO daily_bars (symbol, date) VALUES ('AAPL', '2024-01-05')")
    ensure_research_schema(connection)
    ensure_research_schema(connection)
    assert connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall() == [(1,), (2,), (3,)]
    assert connection.execute("SELECT symbol, date FROM daily_bars").fetchall() == [("AAPL", date(2024, 1, 5))]
    for table, columns in RESEARCH_COLUMNS.items():
        actual = {row[1]: row[2] for row in connection.execute(f"PRAGMA table_info('{table}')").fetchall()}
        assert all(actual.get(name) == kind for name, kind in columns.items())


def test_research_migration_rolls_back_on_incompatible_table() -> None:
    connection = duckdb.connect(":memory:")
    ensure_schema(connection)
    connection.execute("CREATE TABLE daily_features (symbol VARCHAR PRIMARY KEY)")
    with pytest.raises(ValueError, match="incompatible columns"):
        ensure_research_schema(connection)
    assert connection.execute("SELECT version FROM schema_migrations ORDER BY version").fetchall() == [(1,)]
    assert connection.execute("SELECT COUNT(*) FROM information_schema.tables WHERE table_name = 'forward_labels'").fetchone()[0] == 0


def test_v2_feature_table_migrates_to_v3_without_losing_rows() -> None:
    connection = duckdb.connect(":memory:")
    ensure_schema(connection)
    prior_columns = {name: kind for name, kind in RESEARCH_COLUMNS["daily_features"].items()
                     if name not in STRATEGY2_EXTRA_COLUMNS}
    definitions = ", ".join(f"{name} {kind}" for name, kind in prior_columns.items())
    connection.execute(f"CREATE TABLE daily_features ({definitions}, PRIMARY KEY (symbol,date,feature_version))")
    connection.execute("""
        INSERT INTO daily_features (symbol,date,feature_version)
        VALUES ('AAPL','2024-01-05','old')
    """)
    ensure_research_schema(connection)
    assert connection.execute("SELECT symbol FROM daily_features").fetchall() == [("AAPL",)]
    assert connection.execute("SELECT reclaim_ma_5 FROM daily_features").fetchone() == (None,)

"""Idempotence and provenance tests for DuckDB bar writes."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from radar.db import WriteStats, get_connection, upsert_assets, upsert_daily_bars
from radar.models import AssetRecord, DailyBar

UTC = timezone.utc


def bar(symbol: str = "AAPL", **changes: object) -> DailyBar:
    fields = dict(
        symbol=symbol,
        date=date(2024, 1, 5),
        open=10.0,
        high=11.0,
        low=9.0,
        close=10.5,
        volume=1000,
        provider="alpaca",
        feed="sip",
        adjustment="split",
        downloaded_at=datetime(2024, 1, 6, tzinfo=UTC),
    )
    fields.update(changes)
    return DailyBar(**fields)


def asset(symbol: str = "AAPL", **changes: object) -> AssetRecord:
    fields = dict(
        symbol=symbol,
        name="Apple",
        exchange="NASDAQ",
        asset_class="us_equity",
        status="active",
        tradable=True,
        fractionable=True,
        shortable=False,
        easy_to_borrow=False,
        first_seen=datetime(2024, 1, 1, tzinfo=UTC),
        last_seen=datetime(2024, 1, 2, tzinfo=UTC),
        updated_at=datetime(2024, 1, 2, 1, tzinfo=UTC),
    )
    fields.update(changes)
    return AssetRecord(**fields)


def test_bar_upsert_is_idempotent_and_accepts_newer_download() -> None:
    connection = get_connection(":memory:")
    original = bar()
    assert upsert_daily_bars(connection, [original]) == WriteStats(inserted=1)
    assert upsert_daily_bars(connection, [original]) == WriteStats(unchanged=1)
    newer = bar(close=10.8, downloaded_at=original.downloaded_at + timedelta(days=1))
    assert upsert_daily_bars(connection, [newer]) == WriteStats(updated=1)
    assert upsert_daily_bars(connection, [original]) == WriteStats(unchanged=1)
    assert connection.execute("SELECT close FROM daily_bars").fetchone()[0] == 10.8
    assert connection.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0] == 1


def test_bar_provenance_conflict_rolls_back_entire_batch() -> None:
    connection = get_connection(":memory:")
    upsert_daily_bars(connection, [bar()])
    with pytest.raises(ValueError, match="different provenance"):
        upsert_daily_bars(connection, [bar(feed="iex"), bar("MSFT")])
    assert connection.execute("SELECT symbol FROM daily_bars").fetchall() == [("AAPL",)]


def test_same_download_time_cannot_revise_prices() -> None:
    connection = get_connection(":memory:")
    upsert_daily_bars(connection, [bar()])
    with pytest.raises(ValueError, match="same download time"):
        upsert_daily_bars(connection, [bar(close=10.7)])


def test_duplicate_incoming_key_rejected() -> None:
    connection = get_connection(":memory:")
    with pytest.raises(ValueError, match="duplicate"):
        upsert_daily_bars(connection, [bar(), bar()])
    assert connection.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0] == 0


def test_file_connection_creates_parent_and_schema(tmp_path) -> None:
    target = tmp_path / "nested" / "market.duckdb"
    connection = get_connection(target)
    try:
        assert target.is_file()
        assert connection.execute("SELECT version FROM schema_migrations").fetchall() == [(1,)]
    finally:
        connection.close()


def test_asset_upsert_preserves_earliest_and_latest_observations() -> None:
    connection = get_connection(":memory:")
    original = asset()
    assert upsert_assets(connection, [original]) == WriteStats(inserted=1)
    assert upsert_assets(connection, [original]) == WriteStats(unchanged=1)
    old = asset(
        name="stale",
        first_seen=original.first_seen - timedelta(days=1),
        last_seen=original.last_seen - timedelta(hours=1),
    )
    assert upsert_assets(connection, [old]) == WriteStats(updated=1)
    assert connection.execute("SELECT name FROM assets").fetchone()[0] == "Apple"
    fresh = asset(
        name="Apple Inc.",
        last_seen=original.last_seen + timedelta(days=1),
        updated_at=original.updated_at + timedelta(days=1),
    )
    assert upsert_assets(connection, [fresh]) == WriteStats(updated=1)
    row = connection.execute("SELECT name, first_seen, last_seen FROM assets").fetchone()
    assert row[0] == "Apple Inc."
    assert row[1].date() == old.first_seen.date()
    assert row[2].date() == fresh.last_seen.date()
    assert connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 1


def test_duplicate_asset_batch_rejected() -> None:
    connection = get_connection(":memory:")
    with pytest.raises(ValueError, match="duplicate symbols"):
        upsert_assets(connection, [asset(), asset()])
    assert connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 0

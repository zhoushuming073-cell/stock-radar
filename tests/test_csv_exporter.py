"""Behavioral tests for the universe CSV exporter."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar.export.csv_exporter import UNIVERSE_CSV_COLUMNS, export_universe_csv
from radar.models import AssetRecord

UTC = timezone.utc


def make_asset(**overrides) -> AssetRecord:
    """Build a valid AssetRecord with timezone-aware UTC timestamps."""
    payload = {
        "asset_class": "us_equity",
        "status": "active",
        "tradable": True,
        "fractionable": True,
        "shortable": True,
        "easy_to_borrow": True,
        "first_seen": datetime(2024, 1, 1, 12, 0, tzinfo=UTC),
        "last_seen": datetime(2024, 1, 2, 12, 0, tzinfo=UTC),
        "updated_at": datetime(2024, 1, 3, 12, 0, tzinfo=UTC),
    }
    payload.update(overrides)
    return AssetRecord(**payload)


def read_csv(path: Path) -> list[list[str]]:
    with path.open("r", encoding="utf-8", newline="") as stream:
        return list(csv.reader(stream))


def test_header_is_exact_and_rows_are_sorted_by_symbol(tmp_path: Path) -> None:
    destination = tmp_path / "universe.csv"
    assets = [
        make_asset(symbol="TSLA", name="Tesla Inc", exchange="NASDAQ"),
        make_asset(symbol="AAPL", name="Apple Inc", exchange="NASDAQ"),
        make_asset(symbol="BRK.B", name="Berkshire", exchange="NYSE"),
        make_asset(symbol="MSFT", name="Microsoft", exchange="NASDAQ"),
    ]

    written = export_universe_csv(assets, destination)

    assert written == 4
    rows = read_csv(destination)
    assert rows[0] == list(UNIVERSE_CSV_COLUMNS)
    assert [row[0] for row in rows[1:]] == ["AAPL", "BRK.B", "MSFT", "TSLA"]
    assert rows[1] == [
        "AAPL",
        "Apple Inc",
        "NASDAQ",
        "us_equity",
        "true",
        "true",
        "true",
    ]


def test_boolean_and_nullable_cells(tmp_path: Path) -> None:
    destination = tmp_path / "universe.csv"

    export_universe_csv(
        [
            make_asset(
                symbol="AAPL",
                name=None,
                exchange="NASDAQ",
                tradable=True,
                fractionable=False,
                shortable=False,
            ),
            make_asset(
                symbol="MSFT",
                name="Microsoft",
                exchange=None,
                tradable=False,
                fractionable=True,
                shortable=True,
            ),
        ],
        destination,
    )

    rows = read_csv(destination)
    assert rows[1] == ["AAPL", "", "NASDAQ", "us_equity", "true", "false", "false"]
    assert rows[2] == ["MSFT", "Microsoft", "", "us_equity", "false", "true", "true"]


def test_empty_input_writes_header_only(tmp_path: Path) -> None:
    destination = tmp_path / "universe.csv"

    written = export_universe_csv([], destination)

    assert written == 0
    assert read_csv(destination) == [list(UNIVERSE_CSV_COLUMNS)]


def test_duplicate_symbol_raises_and_keeps_existing_csv(tmp_path: Path) -> None:
    destination = tmp_path / "universe.csv"
    export_universe_csv([make_asset(symbol="AAPL")], destination)
    before = destination.read_text(encoding="utf-8")

    with pytest.raises(ValueError, match="duplicate symbol"):
        export_universe_csv(
            [
                make_asset(symbol="AAPL", name="Apple Inc"),
                make_asset(symbol="AAPL", name="Apple Inc (dup)"),
            ],
            destination,
        )

    assert destination.read_text(encoding="utf-8") == before
    assert read_csv(destination)[1][0] == "AAPL"
    assert list(tmp_path.iterdir()) == [destination]


def test_nested_parent_directory_is_created(tmp_path: Path) -> None:
    destination = tmp_path / "artifacts" / "nested" / "universe.csv"

    written = export_universe_csv([make_asset(symbol="AAPL")], destination)

    assert written == 1
    assert destination.exists()
    assert read_csv(destination)[1][0] == "AAPL"

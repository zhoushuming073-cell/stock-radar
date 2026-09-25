"""Behavioral tests for the Phase 1 initial eligible-universe filter."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from radar.models import AssetRecord
from radar.universe.filters import ELIGIBLE_EXCHANGES, filter_eligible_assets

UTC = timezone.utc


def make_asset(**overrides) -> AssetRecord:
    """Build a valid AssetRecord with timezone-aware UTC timestamps."""
    payload = {
        "asset_class": "us_equity",
        "status": "active",
        "exchange": "NASDAQ",
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


def symbols(assets: list[AssetRecord]) -> list[str]:
    return [asset.symbol for asset in assets]


def test_eligible_asset_is_included() -> None:
    result = filter_eligible_assets([make_asset(symbol="AAPL")])

    assert symbols(result) == ["AAPL"]
    assert result[0].exchange == "NASDAQ"


def test_every_eligible_exchange_is_included() -> None:
    assets = [
        make_asset(symbol=f"SYM{index}", exchange=exchange)
        for index, exchange in enumerate(sorted(ELIGIBLE_EXCHANGES))
    ]

    assert len(filter_eligible_assets(assets)) == len(ELIGIBLE_EXCHANGES)


def test_non_us_equity_asset_class_is_excluded() -> None:
    assets = [
        make_asset(symbol="AAPL"),
        make_asset(symbol="BTCUSD", asset_class="crypto"),
        make_asset(symbol="ES", asset_class="us_equity_option"),
    ]

    assert symbols(filter_eligible_assets(assets)) == ["AAPL"]


def test_inactive_status_is_excluded() -> None:
    assets = [
        make_asset(symbol="AAPL"),
        make_asset(symbol="DELIST", status="inactive"),
        make_asset(symbol="SUSP", status="suspended"),
    ]

    assert symbols(filter_eligible_assets(assets)) == ["AAPL"]


def test_non_tradable_asset_is_excluded() -> None:
    assets = [
        make_asset(symbol="AAPL"),
        make_asset(symbol="HALT", tradable=False),
    ]

    assert symbols(filter_eligible_assets(assets)) == ["AAPL"]


def test_otc_and_unknown_exchanges_are_excluded() -> None:
    assets = [
        make_asset(symbol="AAPL", exchange="NASDAQ"),
        make_asset(symbol="PINK", exchange="OTC"),
        make_asset(symbol="IEX", exchange="IEX"),
    ]

    assert symbols(filter_eligible_assets(assets)) == ["AAPL"]


def test_missing_exchange_is_excluded() -> None:
    assets = [
        make_asset(symbol="AAPL", exchange="NASDAQ"),
        make_asset(symbol="NOEXCH", exchange=None),
    ]

    assert symbols(filter_eligible_assets(assets)) == ["AAPL"]


def test_case_and_whitespace_are_normalized() -> None:
    assets = [
        make_asset(symbol="AAPL", asset_class="US_Equity", status=" Active "),
        make_asset(symbol="MSFT", exchange=" nasdaq "),
        make_asset(symbol="SPY", exchange="Arca"),
    ]

    assert symbols(filter_eligible_assets(assets)) == ["AAPL", "MSFT", "SPY"]


def test_output_is_sorted_by_symbol() -> None:
    assets = [
        make_asset(symbol="TSLA", exchange="NASDAQ"),
        make_asset(symbol="AAPL", exchange="NASDAQ"),
        make_asset(symbol="BRK.B", exchange="NYSE"),
        make_asset(symbol="MSFT", exchange="NASDAQ"),
    ]

    assert symbols(filter_eligible_assets(assets)) == ["AAPL", "BRK.B", "MSFT", "TSLA"]


def test_duplicate_symbol_is_rejected() -> None:
    with pytest.raises(ValueError, match="duplicate symbol"):
        filter_eligible_assets(
            [
                make_asset(symbol="AAPL", name="Apple Inc"),
                make_asset(symbol="AAPL", name="Apple Inc (dup)"),
            ]
        )


def test_duplicate_symbol_is_rejected_even_when_filtered_out() -> None:
    with pytest.raises(ValueError, match="duplicate symbol"):
        filter_eligible_assets(
            [
                make_asset(symbol="PINK", exchange="OTC"),
                make_asset(symbol="PINK", exchange="OTC", name="other snapshot"),
            ]
        )


def test_empty_input_returns_empty_list() -> None:
    assert filter_eligible_assets([]) == []


def test_all_ineligible_input_returns_empty_list() -> None:
    assets = [
        make_asset(symbol="BTCUSD", asset_class="crypto"),
        make_asset(symbol="HALT", tradable=False),
        make_asset(symbol="PINK", exchange="OTC"),
        make_asset(symbol="OLD", status="inactive"),
    ]

    assert filter_eligible_assets(assets) == []


def test_input_is_not_mutated() -> None:
    assets = [make_asset(symbol="AAPL"), make_asset(symbol="BTCUSD", asset_class="crypto")]
    snapshot = list(assets)

    filter_eligible_assets(assets)

    assert assets == snapshot

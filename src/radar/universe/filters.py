"""Phase 1 initial eligible-universe filter.

This is the first, deliberately coarse screen applied to the provider asset
master. It keeps only US-equity assets that are active, tradable and listed on
one of the major US exchanges, and it is pure in-memory logic: no network and
no database access.

The screen is *not* a common-stock-only filter. ETFs, ADRs, preferred shares
and other US-listed equity-like classes that satisfy the rules below remain in
the universe; narrowing further belongs to a later phase.
"""

from __future__ import annotations

from collections.abc import Iterable

from ..models import AssetRecord

ELIGIBLE_ASSET_CLASS = "us_equity"
ELIGIBLE_STATUS = "active"
ELIGIBLE_EXCHANGES = frozenset({"NASDAQ", "NYSE", "AMEX", "ARCA", "BATS"})


def _normalized(value: str | None) -> str | None:
    """Trim + uppercase a text field for case-insensitive comparison."""
    if value is None:
        return None
    return value.strip().upper()


def _is_eligible(asset: AssetRecord) -> bool:
    if _normalized(asset.asset_class) != ELIGIBLE_ASSET_CLASS.upper():
        return False
    if _normalized(asset.status) != ELIGIBLE_STATUS.upper():
        return False
    if not asset.tradable:
        return False
    return _normalized(asset.exchange) in ELIGIBLE_EXCHANGES


def filter_eligible_assets(assets: Iterable[AssetRecord]) -> list[AssetRecord]:
    """Return the eligible subset of ``assets``, sorted by symbol.

    Class, status and exchange comparisons are case-insensitive; a missing or
    non-major exchange (including OTC) is excluded. Duplicate input symbols are
    rejected with ``ValueError`` instead of silently keeping one snapshot.
    """
    kept: dict[str, AssetRecord] = {}
    seen: set[str] = set()
    for asset in assets:
        if asset.symbol in seen:
            raise ValueError(f"duplicate symbol in asset universe: {asset.symbol!r}")
        seen.add(asset.symbol)
        if _is_eligible(asset):
            kept[asset.symbol] = asset

    return [kept[symbol] for symbol in sorted(kept)]

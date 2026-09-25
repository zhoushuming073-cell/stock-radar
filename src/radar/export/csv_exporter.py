"""CSV export helpers for radar research artifacts."""

from __future__ import annotations

import csv
import os
import tempfile
from collections.abc import Iterable
from pathlib import Path

from ..models import AssetRecord

UNIVERSE_CSV_COLUMNS = (
    "symbol",
    "name",
    "exchange",
    "asset_class",
    "tradable",
    "fractionable",
    "shortable",
)


def _cell(value: str | None) -> str:
    """Render a nullable text column as a CSV cell (None -> empty)."""
    return "" if value is None else value


def _flag(value: bool) -> str:
    return "true" if value else "false"


def export_universe_csv(assets: Iterable[AssetRecord], path: str | Path) -> int:
    """Write the tradable universe to ``path`` as UTF-8 CSV.

    Rows are sorted by symbol and duplicate symbols are rejected, so the output
    is deterministic for a given input set. The file is written to a temporary
    file in the target directory and atomically renamed into place, so readers
    never observe a partially written universe file.

    Returns the number of data rows written (header excluded).
    """
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)

    rows: dict[str, tuple[str, ...]] = {}
    for asset in assets:
        if asset.symbol in rows:
            raise ValueError(f"duplicate symbol in universe export: {asset.symbol!r}")
        rows[asset.symbol] = (
            asset.symbol,
            _cell(asset.name),
            _cell(asset.exchange),
            asset.asset_class,
            _flag(asset.tradable),
            _flag(asset.fractionable),
            _flag(asset.shortable),
        )

    ordered = [rows[symbol] for symbol in sorted(rows)]

    handle, temp_name = tempfile.mkstemp(
        dir=str(destination.parent), prefix=f".{destination.name}.", suffix=".tmp"
    )
    try:
        with os.fdopen(handle, "w", encoding="utf-8", newline="") as stream:
            writer = csv.writer(stream, lineterminator="\n")
            writer.writerow(UNIVERSE_CSV_COLUMNS)
            writer.writerows(ordered)
        os.replace(temp_name, destination)
    except BaseException:
        try:
            os.unlink(temp_name)
        except OSError:
            pass
        raise

    return len(ordered)

"""Read causal market inputs for Strategy Lab workers from DuckDB."""

from __future__ import annotations

from pathlib import Path

import duckdb
import pandas as pd

from radar.research.pipeline import FEATURE_VERSION


ENGINE_FEATURES = frozenset({
    "avg_dollar_volume_20", "elasticity_score", "drawdown_20",
    "ret_1", "close_location", "tradability_pass",
})


def available_features(database: Path) -> set[str]:
    connection = duckdb.connect(str(database), read_only=True)
    try:
        return {row[1] for row in connection.execute("PRAGMA table_info('daily_features')").fetchall()}
    finally:
        connection.close()


def load_strategy_segment(
    database: Path, start: pd.Timestamp, end: pd.Timestamp,
    required_features: set[str],
) -> pd.DataFrame:
    """Load only current/past feature columns; never join forward_labels."""
    fields = ENGINE_FEATURES | required_features
    connection = duckdb.connect(str(database), read_only=True)
    try:
        available = {row[1] for row in connection.execute("PRAGMA table_info('daily_features')").fetchall()}
        missing = fields - available
        if missing:
            raise ValueError(f"missing causal feature columns: {sorted(missing)}")
        # Identifiers come from the database schema, then are quoted for SQL.
        selected = ", ".join(f'f."{name}"' for name in sorted(fields))
        frame = connection.execute(f"""
            SELECT f.date, f.symbol, b.open, b.close, {selected},
                   a.name AS security_name
            FROM daily_features AS f
            JOIN daily_bars AS b ON f.date=b.date AND f.symbol=b.symbol
            JOIN assets AS a ON f.symbol=a.symbol
            WHERE f.feature_version=? AND f.date BETWEEN ? AND ?
        """, [FEATURE_VERSION, pd.Timestamp(start).date(), pd.Timestamp(end).date()]).df()
    finally:
        connection.close()
    if frame.empty:
        raise ValueError(f"no causal market features from {start} through {end}")
    frame["date"] = pd.to_datetime(frame["date"])
    if frame.duplicated(["date", "symbol"]).any():
        raise ValueError("duplicate market feature for one symbol/session")
    return frame.set_index(["date", "symbol"], drop=False).sort_index()


def source_watermark(database: Path) -> str | None:
    connection = duckdb.connect(str(database), read_only=True)
    try:
        value = connection.execute("SELECT MAX(downloaded_at) FROM daily_bars").fetchone()[0]
        return value.isoformat() if value is not None else None
    finally:
        connection.close()

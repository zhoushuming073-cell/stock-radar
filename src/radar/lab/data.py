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
MARKET_FEATURE_VERSION = "causal-market-v1"
MARKET_FEATURES = frozenset({
    "spy_trend", "qqq_trend", "spy_drawdown", "qqq_drawdown",
    "market_realized_volatility", "market_breadth",
})


def available_features(database: Path) -> set[str]:
    connection = duckdb.connect(str(database), read_only=True)
    try:
        return ({row[1] for row in connection.execute("PRAGMA table_info('daily_features')").fetchall()}
                | MARKET_FEATURES)
    finally:
        connection.close()


def load_strategy_segment(
    database: Path, start: pd.Timestamp, end: pd.Timestamp,
    required_features: set[str],
) -> pd.DataFrame:
    """Load only current/past feature columns; never join forward_labels."""
    fields = ENGINE_FEATURES | (required_features - MARKET_FEATURES)
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
        context = None
        if required_features & MARKET_FEATURES:
            benchmark = connection.execute("""
                SELECT date, symbol, close FROM daily_bars
                WHERE symbol IN ('SPY','QQQ') AND date<=? ORDER BY date
            """, [pd.Timestamp(end).date()]).df()
            breadth = connection.execute("""
                SELECT date, AVG(CASE WHEN dist_ma_20>0 THEN 1.0 ELSE 0.0 END) AS market_breadth
                FROM daily_features WHERE feature_version=? AND date BETWEEN ? AND ?
                  AND dist_ma_20 IS NOT NULL AND tradability_pass
                GROUP BY date
            """, [FEATURE_VERSION, pd.Timestamp(start).date(), pd.Timestamp(end).date()]).df()
            context = _market_context(benchmark, breadth)
    finally:
        connection.close()
    if frame.empty:
        raise ValueError(f"no causal market features from {start} through {end}")
    frame["date"] = pd.to_datetime(frame["date"])
    if context is not None:
        frame = frame.merge(context, on="date", how="left", validate="many_to_one")
        missing_context = sorted(name for name in required_features & MARKET_FEATURES
                                 if frame[name].isna().any())
        if missing_context:
            raise ValueError(f"market context unavailable: {missing_context}")
    if frame.duplicated(["date", "symbol"]).any():
        raise ValueError("duplicate market feature for one symbol/session")
    return frame.set_index(["date", "symbol"], drop=False).sort_index()


def _market_context(benchmark: pd.DataFrame, breadth: pd.DataFrame) -> pd.DataFrame:
    if benchmark.empty:
        raise ValueError("SPY/QQQ history required for market context")
    benchmark["date"] = pd.to_datetime(benchmark["date"])
    pieces = []
    for symbol in ("SPY", "QQQ"):
        part = benchmark.loc[benchmark["symbol"] == symbol, ["date", "close"]].copy()
        part = part.sort_values("date").drop_duplicates("date")
        if part.empty:
            raise ValueError(f"{symbol} history required for market context")
        close = part["close"].astype(float)
        prefix = symbol.lower()
        part[f"{prefix}_trend"] = close / close.rolling(20, min_periods=20).mean() - 1
        part[f"{prefix}_drawdown"] = close / close.rolling(60, min_periods=60).max() - 1
        if symbol == "SPY":
            part["market_realized_volatility"] = (close.pct_change().rolling(20, min_periods=20)
                                                   .std() * (252 ** 0.5))
        pieces.append(part.drop(columns="close"))
    breadth = breadth.copy()
    breadth["date"] = pd.to_datetime(breadth["date"])
    return pieces[0].merge(pieces[1], on="date", how="outer", validate="one_to_one").merge(
        breadth, on="date", how="left", validate="one_to_one")


def load_forward_bars(database: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Host-only OHLC; callers must never pass this frame to a plugin."""
    with duckdb.connect(str(database), read_only=True) as connection:
        bars = connection.execute("""
            SELECT date,symbol,open,high,low,close FROM daily_bars
            WHERE date BETWEEN ? AND ? ORDER BY date,symbol
        """, [pd.Timestamp(start).date(), pd.Timestamp(end).date()]).df()
    bars["date"] = pd.to_datetime(bars["date"])
    return bars


def source_watermark(database: Path) -> str | None:
    connection = duckdb.connect(str(database), read_only=True)
    try:
        value = connection.execute("SELECT MAX(downloaded_at) FROM daily_bars").fetchone()[0]
        return value.isoformat() if value is not None else None
    finally:
        connection.close()

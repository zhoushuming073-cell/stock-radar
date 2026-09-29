"""Slow, physically truncated reference calculation for one signal date.

This is a correctness oracle for the vectorized research tables, not the
production Scanner. It deliberately reads no stock or benchmark bar after t.
"""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import yaml

from radar.features.base import compute_base_features
from radar.features.elasticity import ElasticityConfig, compute_elasticity_inputs
from radar.features.scoring import (COMPONENT_NAMES, load_research_config,
                                    score_elasticity, tradability_gate)
from radar.features.strategy2 import compute_strategy2_features
from radar.schema import RESEARCH_COLUMNS
from radar.strategy.adapter import evaluate_selection
from radar.strategy.base import StrategyPlugin


RAW_COLUMNS = ["elasticity_beta_raw", "elasticity_atr_raw", "elasticity_idio_raw",
               "elasticity_burst_raw", "elasticity_hit_raw"]


def strict_asof_day(connection: duckdb.DuckDBPyConnection, day: pd.Timestamp,
                    config_path: Path, symbols: list[str] | None = None) -> pd.DataFrame:
    """Recalculate U_t and scores from bars at or before *day* only.

    The optional fixed symbol list freezes the current survivor cohort for
    mutation tests. It does not turn that cohort into historical PIT coverage.
    """
    day = pd.Timestamp(day).normalize()
    if symbols is None:
        symbols = [row[0] for row in connection.execute("""
            SELECT a.symbol FROM assets a
            WHERE a.symbol NOT IN ('SPY','QQQ')
              AND upper(trim(a.asset_class))='US_EQUITY'
              AND upper(trim(a.status))='ACTIVE'
              AND EXISTS (SELECT 1 FROM daily_bars b WHERE b.symbol=a.symbol AND b.date<=?)
            ORDER BY a.symbol
        """, [day.date()]).fetchall()]
    if any(symbol in {"SPY", "QQQ"} for symbol in symbols):
        raise ValueError("benchmark symbols cannot enter the stock cohort")
    benchmark = connection.execute("""
        SELECT symbol,date,close FROM daily_bars
        WHERE symbol IN ('SPY','QQQ') AND date<=? ORDER BY date
    """, [day.date()]).df()
    if benchmark.empty:
        raise ValueError("SPY and QQQ history is required")
    benchmark["date"] = pd.to_datetime(benchmark["date"])
    closes = {symbol: benchmark.loc[benchmark.symbol.eq(symbol)].set_index("date")["close"]
              for symbol in ("SPY", "QQQ")}
    if any(series.empty for series in closes.values()):
        raise ValueError("SPY and QQQ history is required")
    sessions = closes["SPY"].index
    if day not in sessions:
        raise ValueError("signal date is not an SPY trading session")
    settings = yaml.safe_load(config_path.read_text(encoding="utf-8"))["elasticity"]
    elasticity_cfg = ElasticityConfig(
        history_window=int(settings["history_window"]),
        history_min=int(settings["history_min"]),
        burst_quantile=float(settings["burst_quantile"]),
        hit_5_weight=float(settings["hit_5_weight"]),
        hit_10_weight=float(settings["hit_10_weight"]),
    )
    cfg = load_research_config(config_path)
    parts = []
    for symbol in symbols:
        raw = connection.execute("""
            SELECT date,open,high,low,close,volume FROM daily_bars
            WHERE symbol=? AND date<=? ORDER BY date
        """, [symbol, day.date()]).df()
        if raw.empty:
            continue
        raw["date"] = pd.to_datetime(raw["date"])
        bars = raw.set_index("date").reindex(sessions)
        if pd.isna(bars.loc[day, "close"]):
            continue
        base = compute_base_features(bars)
        elastic = compute_elasticity_inputs(bars, closes["SPY"], closes["QQQ"], elasticity_cfg)
        strategy = compute_strategy2_features(bars, closes["SPY"], closes["QQQ"])
        feature = pd.concat([base, elastic, strategy], axis=1)
        feature["elasticity_atr_raw"] = feature["atr_pct_20"]
        eligible = tradability_gate(pd.DataFrame({
            "close": bars["close"],
            "avg_dollar_volume_20": feature["avg_dollar_volume_20"],
            "history_sessions": bars["close"].notna().cumsum(),
        }, index=sessions), cfg)
        last = feature.loc[day].to_dict()
        name = connection.execute("SELECT name FROM assets WHERE symbol=?",
                                  [symbol]).fetchone()
        parts.append({"date": day, "symbol": symbol,
                      "security_name": (name[0] or symbol) if name else symbol,
                      "close": float(bars.loc[day, "close"]),
                      "tradability_pass": bool(eligible.loc[day]), **last})
    result = pd.DataFrame(parts)
    if result.empty:
        return result
    result["market_breadth"] = result.loc[
        result.tradability_pass & result.dist_ma_20.notna(), "dist_ma_20"].gt(0).mean()
    for symbol in ("SPY", "QQQ"):
        close = closes[symbol].astype(float).reindex(sessions)
        prefix = symbol.lower()
        result[f"{prefix}_trend"] = (
            close.iloc[-1] / close.iloc[-20:].mean() - 1 if len(close) >= 20 else np.nan)
        result[f"{prefix}_drawdown"] = (
            close.iloc[-1] / close.iloc[-60:].max() - 1 if len(close) >= 60 else np.nan)
        if symbol == "SPY":
            returns = close.pct_change(fill_method=None)
            result["market_realized_volatility"] = (
                returns.iloc[-20:].std(ddof=1) * np.sqrt(252)
                if len(returns) >= 21 else np.nan)
    component_columns = [f"elasticity_{name}_component" for name in COMPONENT_NAMES.values()]
    for name in [*component_columns, "elasticity_score"]:
        result[name] = float("nan")
    eligible = result.loc[result.tradability_pass].copy()
    if not eligible.empty:
        scored = score_elasticity(eligible, cfg)
        result.loc[scored.index, [*component_columns, "elasticity_score"]] = scored[
            [*component_columns, "elasticity_score"]]
    result = result.sort_values(["elasticity_score", "symbol"],
                                ascending=[False, True], na_position="last")
    result["rank"] = range(1, len(result) + 1)
    result.loc[result.elasticity_score.isna(), "rank"] = pd.NA
    for name in RESEARCH_COLUMNS["daily_features"]:
        if name not in result and name not in {"feature_version", "computed_at"}:
            result[name] = np.nan  # the materialized table stores absent fields as NULL
    return result.reset_index(drop=True)


def strict_strategy_day(connection: duckdb.DuckDBPyConnection,
                        day: pd.Timestamp, config_path: Path,
                        plugin: StrategyPlugin, config: dict,
                        symbols: list[str] | None = None) -> pd.DataFrame:
    """Run the production plugin adapter over the physically truncated day."""
    daily = strict_asof_day(connection, day, config_path, symbols)
    if daily.empty:
        return daily
    eligible = daily.loc[daily.tradability_pass].sort_values("symbol").copy()
    for name in plugin.required_features():
        if name in eligible and pd.api.types.is_numeric_dtype(eligible[name]):
            eligible = eligible.loc[np.isfinite(pd.to_numeric(
                eligible[name], errors="coerce"))]
    ranked, _ = evaluate_selection(plugin, config, eligible)
    return ranked

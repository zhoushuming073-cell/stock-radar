"""Future mutation and strict-vs-fast causal research contracts."""

from __future__ import annotations

from pathlib import Path
import shutil

import duckdb
import numpy as np
import pandas as pd
import pytest

from radar.lab.data import load_strategy_segment
from radar.research.asof import RAW_COLUMNS, strict_asof_day, strict_strategy_day
from radar.research.pipeline import BUILD_FEATURE_VERSION, build_research_tables
from radar.schema import ensure_schema
from radar.strategy.adapter import evaluate_selection
from radar.strategy.base import StrategyPlugin
from scripts.verify_asof_build import verify


class CausalRankPlugin(StrategyPlugin):
    def required_features(self) -> set[str]:
        return {"elasticity_score", "dist_ma_20", "market_breadth"}

    def hard_filter(self, context, config):
        return context.frame["dist_ma_20"].notna()

    def score(self, context, config):
        return context.frame["elasticity_score"] + context.frame["market_breadth"]

    def select(self, candidates, config):
        return candidates.sort_values(["strategy_score", "symbol"],
                                      ascending=[False, True]).head(2)


def _fixture_database(path: Path) -> pd.DatetimeIndex:
    sessions = pd.bdate_range("2025-01-02", periods=200)
    with duckdb.connect(str(path)) as connection:
        ensure_schema(connection)
        for symbol in ("SPY", "QQQ", "AAA", "BBB", "CCC", "OLD"):
            connection.execute("""
                INSERT INTO assets(symbol,name,asset_class,status,tradable,exchange)
                VALUES (?,?,'US_EQUITY','ACTIVE',true,'NYSE')
            """, [symbol, symbol])
        rows = []
        for i, day in enumerate(sessions):
            for symbol, offset, volume in (("SPY", 0, 10_000_000),
                                           ("QQQ", 5, 10_000_000),
                                           ("AAA", 2, 1_000_000),
                                           ("BBB", 3, 900_000),
                                           ("CCC", -8, 50_000),
                                           ("OLD", 4, 800_000)):
                if symbol == "OLD" and i > 140:
                    continue
                close = 12 + offset + i * .025 + .4 * np.sin(i / 5 + offset)
                rows.append((symbol, day.date(), close * .99, close * 1.01,
                             close * .98, close, volume, "alpaca", "sip", "split"))
        connection.executemany("""
            INSERT INTO daily_bars(symbol,date,open,high,low,close,volume,
                                   provider,feed,adjustment,downloaded_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,current_timestamp)
        """, rows)
    return sessions


def _fast_day(database: Path, day: pd.Timestamp) -> pd.DataFrame:
    with duckdb.connect(str(database), read_only=True) as connection:
        frame = connection.execute("""
            SELECT symbol,date,tradability_pass,dist_ma_20,
                   elasticity_beta_raw,elasticity_atr_raw,elasticity_idio_raw,
                   elasticity_burst_raw,elasticity_hit_raw,
                   elasticity_beta_component,elasticity_atr_component,
                   elasticity_idio_component,elasticity_burst_component,
                   elasticity_hit_component,elasticity_score
            FROM daily_features WHERE feature_version=? AND date=? ORDER BY symbol
        """, [BUILD_FEATURE_VERSION, day.date()]).df()
    return frame


def _assert_same(first: pd.DataFrame, second: pd.DataFrame) -> None:
    first = first.sort_values("symbol").reset_index(drop=True)
    second = second.sort_values("symbol").reset_index(drop=True)
    assert first.symbol.tolist() == second.symbol.tolist()
    assert first.tradability_pass.tolist() == second.tradability_pass.tolist()
    columns = ["dist_ma_20", *RAW_COLUMNS, "elasticity_beta_component",
               "elasticity_atr_component", "elasticity_idio_component",
               "elasticity_burst_component", "elasticity_hit_component",
               "elasticity_score"]
    for column in columns:
        np.testing.assert_allclose(first[column].astype(float), second[column].astype(float),
                                   equal_nan=True, rtol=1e-10, atol=1e-10)
    first_rank = first.loc[first.elasticity_score.notna()].sort_values(
        ["elasticity_score", "symbol"], ascending=[False, True]).symbol.tolist()
    second_rank = second.loc[second.elasticity_score.notna()].sort_values(
        ["elasticity_score", "symbol"], ascending=[False, True]).symbol.tolist()
    assert first_rank == second_rank


def test_strict_replay_matches_fast_and_ignores_future_mutations(tmp_path):
    database = tmp_path / "research.duckdb"
    changed = tmp_path / "mutated.duckdb"
    config = Path(__file__).resolve().parents[1] / "config/research.yaml"
    sessions = _fixture_database(database)
    day = sessions[140]
    build_research_tables(database, config)
    assert verify(database, config, [day])["passed"] is True
    with duckdb.connect(str(database), read_only=True) as connection:
        strict = strict_asof_day(connection, day, config, ["AAA", "BBB", "CCC", "OLD"])
    fast = _fast_day(database, day)
    _assert_same(fast, strict)
    assert "OLD" in fast.symbol.tolist()  # no bars in the sample's final 35 days
    assert strict.loc[strict.symbol.eq("CCC"), "tradability_pass"].iloc[0] == False
    assert np.isnan(strict.loc[strict.symbol.eq("CCC"), "elasticity_score"].iloc[0])
    np.testing.assert_allclose(sorted(strict.loc[strict.tradability_pass,
                                                  "elasticity_atr_component"].tolist()),
                               [100 / 3, 200 / 3, 100])
    assert strict.market_breadth.iloc[0] == pytest.approx(
        fast.loc[fast.tradability_pass & fast.dist_ma_20.notna(),
                 "dist_ma_20"].gt(0).mean())
    segment = load_strategy_segment(database, day, day, {"market_breadth"},
                                    feature_version=BUILD_FEATURE_VERSION)
    assert segment.market_breadth.iloc[0] == pytest.approx(strict.market_breadth.iloc[0])
    plugin = CausalRankPlugin()
    with duckdb.connect(str(database), read_only=True) as connection:
        strict_candidates = strict_strategy_day(connection, day, config, plugin, {},
                                                ["AAA", "BBB", "CCC", "OLD"])
    fast_daily = load_strategy_segment(
        database, day, day, plugin.required_features(),
        feature_version=BUILD_FEATURE_VERSION)
    fast_daily = fast_daily.loc[fast_daily.tradability_pass &
                                fast_daily.elasticity_score.notna()]
    fast_candidates, _ = evaluate_selection(plugin, {}, fast_daily)
    assert strict_candidates.symbol.tolist() == fast_candidates.symbol.tolist()
    assert strict_candidates["rank"].tolist() == fast_candidates["rank"].tolist()
    assert strict_candidates.selected.tolist() == fast_candidates.selected.tolist()
    np.testing.assert_allclose(strict_candidates.strategy_score,
                               fast_candidates.strategy_score, rtol=1e-12)

    shutil.copy2(database, changed)
    with duckdb.connect(str(changed)) as connection:
        connection.execute("""
            UPDATE daily_bars SET close=close*7, high=high*7, low=low*7,
                                  volume=volume*5 WHERE date>?
        """, [day.date()])
        connection.execute("UPDATE assets SET tradable=false, exchange='OTC'")
        strict_changed = strict_asof_day(connection, day, config,
                                         ["AAA", "BBB", "CCC", "OLD"])
        candidates_changed = strict_strategy_day(connection, day, config, plugin, {},
                                                 ["AAA", "BBB", "CCC", "OLD"])
    _assert_same(strict, strict_changed)
    assert candidates_changed.symbol.tolist() == strict_candidates.symbol.tolist()
    assert candidates_changed["rank"].tolist() == strict_candidates["rank"].tolist()
    np.testing.assert_allclose(candidates_changed.strategy_score,
                               strict_candidates.strategy_score, rtol=1e-12)
    build_research_tables(changed, config)
    assert verify(changed, config, [day])["passed"] is True
    _assert_same(fast, _fast_day(changed, day))

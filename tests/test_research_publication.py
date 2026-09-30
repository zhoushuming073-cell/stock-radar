"""Frozen split and atomic research-publication regressions."""

from __future__ import annotations

import hashlib
from pathlib import Path

import duckdb
import pandas as pd
import pytest
import yaml

from radar.research.pipeline import BUILD_FEATURE_VERSION, build_research_tables
from radar.research.splits import resolve_split_windows
from radar.schema import ensure_schema


ROOT = Path(__file__).resolve().parents[1]


def test_appending_sessions_cannot_reclassify_frozen_history():
    config = yaml.safe_load((ROOT / "config/research.yaml").read_text(encoding="utf-8"))["research"]
    original = pd.bdate_range("2021-09-01", "2026-09-28")
    appended = original.append(pd.bdate_range("2026-09-29", periods=30))
    before = resolve_split_windows(original, config)
    after = resolve_split_windows(appended, config)
    for name in ("train", "validation", "test"):
        assert before[name] == after[name]
    assert "fresh_oos" not in before
    assert after["fresh_oos"][0] > before["test"][2]
    assert after["fresh_oos"][1] < after["fresh_oos"][2]


def test_production_splits_do_not_fall_back_to_fractions():
    sessions = pd.bdate_range("2025-01-01", periods=100)
    with pytest.raises(ValueError, match="frozen_splits"):
        resolve_split_windows(sessions, {"embargo_sessions": 10,
                                         "max_forward_sessions": 10,
                                         "train_fraction": .6,
                                         "validation_fraction": .2})


def _small_store(database: Path, config: Path) -> None:
    sessions = pd.bdate_range("2025-01-02", periods=150)
    with duckdb.connect(str(database)) as connection:
        ensure_schema(connection)
        for symbol in ("SPY", "QQQ", "AAA", "BBB"):
            connection.execute("""
                INSERT INTO assets(symbol,name,asset_class,status,tradable,exchange)
                VALUES (?,?,'US_EQUITY','ACTIVE',true,'NYSE')
            """, [symbol, symbol])
        rows = []
        for ordinal, day in enumerate(sessions):
            for symbol, offset in (("SPY", 0), ("QQQ", 1), ("AAA", 2), ("BBB", 3)):
                close = 12 + offset + ordinal * .02
                rows.append((symbol, day.date(), close, close * 1.01,
                             close * .99, close, 1_000_000,
                             "alpaca", "sip", "split"))
        connection.executemany("""
            INSERT INTO daily_bars(symbol,date,open,high,low,close,volume,
                                   provider,feed,adjustment,downloaded_at)
            VALUES (?,?,?,?,?,?,?,?,?,?,current_timestamp)
        """, rows)
    settings = yaml.safe_load((ROOT / "config/research.yaml").read_text(encoding="utf-8"))
    settings["research"].pop("frozen_splits")
    settings["research"].pop("split_version")
    settings["research"].update({"allow_fractional_fixture_splits": True,
                                 "train_fraction": .6,
                                 "validation_fraction": .2})
    config.write_text(yaml.safe_dump(settings), encoding="utf-8")


def test_partial_or_interrupted_build_never_changes_active_store(tmp_path):
    database, config = tmp_path / "research.duckdb", tmp_path / "research.yaml"
    _small_store(database, config)
    original = hashlib.sha256(database.read_bytes()).hexdigest()
    partial = build_research_tables(database, config, max_symbols=1)
    assert partial["promoted"] is False
    assert hashlib.sha256(database.read_bytes()).hexdigest() == original

    def interrupt(item: dict) -> None:
        if item["phase"] == "features":
            raise RuntimeError("simulated power loss")

    with pytest.raises(RuntimeError, match="simulated power loss"):
        build_research_tables(database, config, progress=interrupt)
    assert hashlib.sha256(database.read_bytes()).hexdigest() == original
    assert not list(tmp_path.glob("*.staging.duckdb"))

    complete = build_research_tables(database, config)
    assert complete["promoted"] is True
    assert Path(complete["backup_database"]).is_file()
    with duckdb.connect(str(database), read_only=True) as connection:
        assert connection.execute("""
            SELECT COUNT(*) FROM daily_features WHERE feature_version=?
        """, [BUILD_FEATURE_VERSION]).fetchone()[0] == complete["feature_rows"]


def test_successful_promotions_keep_only_configured_recent_backups(tmp_path):
    database, config = tmp_path / "research.duckdb", tmp_path / "research.yaml"
    _small_store(database, config)
    for _ in range(4):
        result = build_research_tables(database, config, backup_retention=2)
        assert result["promoted"] is True
        backups = list((tmp_path / "research-backups").glob("research.*.duckdb"))
        assert len(backups) <= 2
        assert Path(result["backup_database"]) in backups
    assert result["retained_backups"] == 2
    rejected = build_research_tables(database, config, max_symbols=1,
                                     backup_retention=1)
    assert rejected["promoted"] is False
    assert len(list((tmp_path / "research-backups").glob("research.*.duckdb"))) == 2
    assert database.is_file()

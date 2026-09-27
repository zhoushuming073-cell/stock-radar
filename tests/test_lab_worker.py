"""Worker orchestration and read-only feature loading with tiny inputs."""

import hashlib
from pathlib import Path
from types import SimpleNamespace

import duckdb
import pandas as pd
import pytest

from radar.lab import data as data_module
from radar.lab import worker as worker_module
from radar.lab.store import RunStore
from radar.strategy.validation import StrategyManifest


def test_market_loader_uses_read_only_duckdb(tmp_path, monkeypatch):
    database = tmp_path / "small.duckdb"
    with duckdb.connect(str(database)) as connection:
        connection.execute("CREATE TABLE assets(symbol VARCHAR, name VARCHAR)")
        connection.execute("INSERT INTO assets VALUES ('AAA','Alpha')")
        connection.execute("CREATE TABLE daily_bars(date DATE, symbol VARCHAR, open DOUBLE, "
                           "close DOUBLE, downloaded_at TIMESTAMP)")
        connection.execute("INSERT INTO daily_bars VALUES "
                           "('2025-01-02','AAA',10,11,'2025-01-03 10:00:00')")
        connection.execute("CREATE TABLE daily_features(date DATE, symbol VARCHAR, "
                           "feature_version VARCHAR, avg_dollar_volume_20 DOUBLE, "
                           "elasticity_score DOUBLE, drawdown_20 DOUBLE, ret_1 DOUBLE, "
                           "close_location DOUBLE, tradability_pass BOOLEAN)")
        connection.execute("INSERT INTO daily_features VALUES "
                           "('2025-01-02','AAA',?,1000000,80,-0.15,0.01,0.9,true)",
                           [data_module.FEATURE_VERSION])
    before = hashlib.sha256(database.read_bytes()).hexdigest()
    real_connect = duckdb.connect
    modes: list[bool | None] = []

    def checked_connect(*args, **kwargs):
        modes.append(kwargs.get("read_only"))
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(data_module.duckdb, "connect", checked_connect)
    features = data_module.available_features(database)
    assert "drawdown_20" in features
    frame = data_module.load_strategy_segment(
        database, pd.Timestamp("2025-01-02"), pd.Timestamp("2025-01-02"),
        {"drawdown_20"},
    )
    assert len(frame) == 1
    assert frame.iloc[0]["symbol"] == "AAA"
    assert "forward_labels" not in frame.columns
    assert data_module.source_watermark(database) == "2025-01-03T10:00:00"
    assert modes == [True, True, True]
    assert hashlib.sha256(database.read_bytes()).hexdigest() == before
    with pytest.raises(ValueError, match="missing causal feature"):
        data_module.load_strategy_segment(
            database, pd.Timestamp("2025-01-02"), pd.Timestamp("2025-01-02"),
            {"unavailable_feature"},
        )


@pytest.fixture
def worker_setup(tmp_path, monkeypatch):
    root = tmp_path / "project"
    for relative in (
        "data/phase2-research.duckdb", "config/backtest.yaml", "config/research.yaml",
        "strategies/tiny_strategy/strategy.py", "src/radar/backtest/engine.py",
        "src/radar/strategy/adapter.py", "src/radar/strategy/full_strategy2.py",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(relative, encoding="utf-8")
    store = RunStore(tmp_path / "runs.sqlite3")
    days = tuple(pd.Timestamp(day) for day in (
        "2025-01-02", "2025-01-03", "2025-01-04"
    ))
    manifest = StrategyManifest.model_validate({
        "name": "Tiny", "id": "tiny_strategy", "version": "1.0.0",
        "interface_version": 1, "author": {"type": "ai", "name": "Test"},
        "description": "Test", "required_features": [],
    })
    monkeypatch.setattr(worker_module, "source_watermark", lambda _path: "watermark")
    monkeypatch.setattr(worker_module, "available_features", lambda _path: set())
    monkeypatch.setattr(worker_module, "load_strategy_directory", lambda *_a, **_kw:
                        SimpleNamespace(manifest=manifest, plugin=object()))
    monkeypatch.setattr(worker_module, "split_dates", lambda *_a: {
        "validation": days, "sessions": pd.DatetimeIndex(days)
    })
    monkeypatch.setattr(worker_module, "load_strategy_segment", lambda *_a:
                        pd.DataFrame({"date": days[:2], "symbol": ["AAA", "AAA"]}))
    monkeypatch.setattr(worker_module, "load_backtest_config", lambda _path: {
        "max_position_fraction": 0.3, "max_new_candidates": 3,
    })
    monkeypatch.setattr(worker_module, "load_fee_config",
                        lambda _path: SimpleNamespace(profile="test"))
    monkeypatch.setattr(worker_module, "_engine_config", lambda *_a, **_kw:
                        SimpleNamespace(initial_capital=10_000.0))
    monkeypatch.setattr(worker_module, "_rules", lambda _raw: object())
    monkeypatch.setattr(worker_module, "make_candidate_selector", lambda *_a, **_kw:
                        lambda *_args: pd.DataFrame())
    monkeypatch.setattr(worker_module, "summarize_backtest", lambda *_a:
                        {"final_equity": 10_100.0})

    def metadata():
        return {
            "strategy_id": "tiny_strategy", "strategy_version": "1.0.0",
            "plugin_interface_version": 1,
            "strategy_path": str(root / "strategies/tiny_strategy"),
            "strategy_code_hash": worker_module.sha256_file(root / "strategies/tiny_strategy/strategy.py"),
            "engine_code_hash": worker_module.sha256_file(root / "src/radar/backtest/engine.py"),
            "adapter_code_hash": worker_module.sha256_file(root / "src/radar/strategy/adapter.py"),
            "legacy_strategy_code_hash": worker_module.sha256_file(
                root / "src/radar/strategy/full_strategy2.py"
            ),
            "config": {"selection": {"max_candidates": 3}},
            "config_hash": "config-hash", "git_revision": "revision",
            "feature_version": worker_module.FEATURE_VERSION,
            "data_snapshot": worker_module.sha256_file(root / "data/phase2-research.duckdb"),
            "source_watermark": "watermark", "fee_profile": "test",
            "slippage_bps": 10.0,
            "backtest_config_hash": worker_module.sha256_file(root / "config/backtest.yaml"),
            "research_config_hash": worker_module.sha256_file(root / "config/research.yaml"),
            "execution_policy": {"entry": "next_open"},
            "split": "validation", "window": [str(day.date()) for day in days],
            "start_date": str(days[0].date()), "end_date": str(days[1].date()),
            "evaluation_end": str(days[2].date()),
        }

    return root, store, metadata


def test_two_identical_worker_runs_persist_identical_results(worker_setup, monkeypatch):
    root, store, metadata = worker_setup

    def run_backtest(*_args, **kwargs):
        for index, day in enumerate((pd.Timestamp("2025-01-02"),
                                     pd.Timestamp("2025-01-03")), 1):
            kwargs["progress_callback"]({
                "date": day, "completed_sessions": index, "total_sessions": 2,
                "equity": 10_000.0 + 50 * index, "open_positions": 1,
                "latest_signals": ["AAA"],
            })
            assert not kwargs["cancel_requested"]()
        return SimpleNamespace(
            equity=pd.DataFrame([{"date": "2025-01-02", "equity": 10_050.0},
                                 {"date": "2025-01-03", "equity": 10_100.0}]),
            trades=pd.DataFrame([{"symbol": "AAA", "net_pnl": 100.0}]),
            orders=pd.DataFrame([{"symbol": "AAA", "side": "buy"}]),
            open_positions=[],
        )

    monkeypatch.setattr(worker_module, "run_backtest", run_backtest)
    first, second = store.create_run(metadata()), store.create_run(metadata())
    worker_module.execute_run(root, store.path, first)
    worker_module.execute_run(root, store.path, second)
    assert store.get_run(first)["status"] == store.get_run(second)["status"] == "completed"
    pd.testing.assert_frame_equal(store.get_equity(first), store.get_equity(second))
    pd.testing.assert_frame_equal(store.get_trades(first), store.get_trades(second))
    assert store.get_run(first)["metrics"] == store.get_run(second)["metrics"]
    assert len(store.get_events(first).query("kind == 'progress'")) == 2


def test_worker_applies_queued_stop_loss_override(worker_setup, monkeypatch):
    root, store, metadata = worker_setup
    details = metadata()
    details["config"]["execution"] = {"stop_loss": -0.20}
    details["execution_policy"] = {"stop_loss": -0.20}
    monkeypatch.setattr(worker_module, "load_backtest_config", lambda _path: {
        "stop_loss": -0.10, "max_position_fraction": 0.3,
        "max_new_candidates": 3,
    })
    captured = {}

    def engine_config(raw, **_kwargs):
        captured["stop_loss"] = raw["stop_loss"]
        return SimpleNamespace(initial_capital=10_000.0)

    monkeypatch.setattr(worker_module, "_engine_config", engine_config)
    monkeypatch.setattr(worker_module, "run_backtest", lambda *_args, **_kwargs:
                        SimpleNamespace(
                            equity=pd.DataFrame(), trades=pd.DataFrame(),
                            orders=pd.DataFrame(), open_positions=[],
                        ))
    run_id = store.create_run(details)
    worker_module.execute_run(root, store.path, run_id)
    assert captured["stop_loss"] == -0.20
    assert store.get_run(run_id)["status"] == "completed"


def test_worker_cancellation_and_changed_source_fail_cleanly(worker_setup, monkeypatch):
    root, store, metadata = worker_setup
    cancelled = store.create_run(metadata())

    def cancel_backtest(*_args, **kwargs):
        store.request_cancel(cancelled)
        assert kwargs["cancel_requested"]()
        raise worker_module.BacktestCancelled()

    monkeypatch.setattr(worker_module, "run_backtest", cancel_backtest)
    assert worker_module.execute_run(root, store.path, cancelled) == {"status": "cancelled"}
    assert store.get_run(cancelled)["status"] == "cancelled"

    changed = store.create_run(metadata())
    (root / "src/radar/backtest/engine.py").write_text("changed", encoding="utf-8")
    with pytest.raises(ValueError, match="source changed"):
        worker_module.execute_run(root, store.path, changed)
    assert store.get_run(changed)["status"] == "failed"
    assert store.get_equity(changed).empty

"""Persistence, immutability and concurrent progress tests for RunStore."""

from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime
import sqlite3
from threading import Barrier

import pandas as pd
import pytest

from radar.lab.store import RunStore, RunStoreError


def _metadata(**updates):
    value = {
        "strategy_id": "full_strategy2_v1",
        "strategy_version": "1.0.0",
        "plugin_interface_version": 1,
        "strategy_path": "strategies/full_strategy2_v1",
        "strategy_code_hash": "strategy-hash",
        "config": {"selection": {"max_candidates": 3}},
        "config_hash": "abc123",
        "git_revision": "deadbeef",
        "feature_version": "phase2-v1",
        "data_snapshot": "sha256:sample",
        "source_watermark": "2026-09-24",
        "fee_profile": "test",
        "slippage_bps": 10,
        "execution_policy": {"entry": "next_open"},
        "backtest_config_hash": "backtest-hash",
        "research_config_hash": "research-hash",
        "start_date": "2025-01-01",
        "end_date": "2025-12-31",
        "evaluation_end": "2026-01-15",
        "split": "Validation",
        "window": ["2025-01-01", "2025-12-31", "2026-01-15"],
    }
    value.update(updates)
    return value


def test_status_progress_results_survive_reopen(tmp_path):
    path = tmp_path / "runs.sqlite"
    store = RunStore(path)
    run_id = store.create_run(_metadata())
    assert store.get_run(run_id)["status"] == "queued"
    store.start_run(run_id, 1234)
    store.start_run(run_id, 1234)
    with pytest.raises(RunStoreError):
        store.start_run(run_id, 5678)
    store.append_progress(run_id, {
        "date": pd.Timestamp("2025-01-03"), "equity": 10_100.0,
        "open_positions": 2, "latest_signals": ["ABC"],
        "completed_sessions": 2, "total_sessions": 10,
    })
    reopened = RunStore(path)
    active = reopened.get_run(run_id)
    assert active["status"] == "running"
    assert active["worker_pid"] == 1234
    assert active["current_date"] == "2025-01-03T00:00:00"
    assert active["positions"] == 2
    assert active["latest_signals"] == ["ABC"]
    assert active["metadata"] == _metadata()
    daily = reopened.get_daily_snapshots(run_id)
    assert len(daily) == 1
    assert daily[0]["date"] == "2025-01-03T00:00:00"
    assert reopened.get_daily_snapshots(run_id, after_event_id=daily[0]["event_id"]) == []

    class Result:
        equity = pd.DataFrame([{"date": pd.Timestamp("2025-01-03"), "equity": 10_100.0}])
        trades = pd.DataFrame([{"symbol": "ABC", "net_pnl": 100.0}])
        orders = pd.DataFrame([{"symbol": "ABC", "side": "buy"}])
        open_positions = []

    # A normal engine result is a dataclass instance with these attributes.
    result = Result()
    result.__dict__.update({
        "equity": Result.equity, "trades": Result.trades,
        "orders": Result.orders, "open_positions": [],
    })
    reopened.finish_run(run_id, result, {"final_equity": 10_100.0, "sharpe": float("nan")})
    completed = RunStore(path).get_run(run_id)
    assert completed["status"] == "completed"
    assert completed["metrics"] == {"final_equity": 10_100.0, "sharpe": None}
    assert completed["result"] == {"open_positions": []}
    assert store.get_equity(run_id).to_dict("records") == [
        {"date": "2025-01-03T00:00:00", "equity": 10_100.0}
    ]
    assert store.get_trades(run_id).to_dict("records") == [
        {"symbol": "ABC", "net_pnl": 100.0}
    ]
    assert "order" in store.get_events(run_id)["kind"].tolist()
    assert store.list_runs(status="completed")[0]["run_id"] == run_id


def test_completed_run_immutable_even_via_direct_sql(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    run_id = store.create_run(_metadata())
    store.start_run(run_id, 42)
    store.finish_run(run_id, {"equity": [{"date": "2025-01-02", "equity": 10.0}],
                              "trades": [], "orders": []}, {"final_equity": 10.0})
    with pytest.raises(RunStoreError):
        store.append_progress(run_id, {"completed_sessions": 1})
    with pytest.raises(RunStoreError):
        store.fail_run(run_id, "late failure")
    with pytest.raises(RunStoreError):
        store.finish_run(run_id, {"equity": []}, {})
    other_id = store.create_run(_metadata(config_hash="new-config"))
    with closing(sqlite3.connect(store.path)) as connection:
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            connection.execute("UPDATE backtest_runs SET status='failed' WHERE run_id=?", (run_id,))
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            connection.execute("INSERT INTO trades(run_id,seq,row_json) VALUES (?,?,?)",
                               (run_id, 0, "{}"))
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            connection.execute("DELETE FROM equity WHERE run_id=?", (run_id,))
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            connection.execute("DELETE FROM events WHERE run_id=?", (run_id,))
        connection.execute("INSERT INTO trades(run_id,seq,row_json) VALUES (?,?,?)",
                           (other_id, 0, "{}"))
        with pytest.raises(sqlite3.DatabaseError, match="immutable"):
            connection.execute("UPDATE trades SET run_id=?,seq=1 WHERE run_id=?",
                               (run_id, other_id))


def test_schema_v1_migrates_to_v6(tmp_path):
    path = tmp_path / "runs.sqlite"
    with closing(sqlite3.connect(path)) as connection:
        RunStore._migrate_v1(connection)
    RunStore(path)
    with closing(sqlite3.connect(path)) as connection:
        assert connection.execute("PRAGMA user_version").fetchone()[0] == 6


def test_cancellation_and_required_metadata(tmp_path):
    store = RunStore(tmp_path / "runs.sqlite")
    with pytest.raises(RunStoreError, match="config_hash"):
        store.create_run({"strategy_id": "incomplete"})
    run_id = store.create_run(_metadata())
    store.start_run(run_id, 4321)
    store.request_cancel(run_id)
    store.request_cancel(run_id)  # idempotent request
    assert store.get_run(run_id)["cancel_requested"] is True
    with pytest.raises(RunStoreError):
        store.finish_run(run_id, {"equity": []}, {})
    store.cancel_run(run_id, "user request")
    assert store.get_run(run_id)["status"] == "cancelled"
    with pytest.raises(RunStoreError):
        store.append_progress(run_id, {"late": True})
    failed_id = store.create_run(_metadata(config_hash="different"))
    store.fail_run(failed_id, "worker failed")
    assert store.get_run(failed_id)["status"] == "failed"
    assert store.get_run(failed_id)["error_text"] == "worker failed"


def test_two_concurrent_progress_writers_are_serialized(tmp_path):
    path = tmp_path / "runs.sqlite"
    store = RunStore(path)
    run_id = store.create_run(_metadata())
    store.start_run(run_id, 1234)
    gate = Barrier(2)

    def write(worker: int) -> None:
        own_store = RunStore(path)
        gate.wait()
        for index in range(25):
            own_store.append_progress(run_id, {
                "worker": worker, "completed_sessions": index,
                "updated": datetime(2025, 1, 1),
            })

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(write, worker) for worker in (1, 2)]
        for future in futures:
            future.result(timeout=30)
    progress_events = store.get_events(run_id).query("kind == 'progress'").to_dict("records")
    assert len(progress_events) == 50
    assert {event["payload"]["worker"] for event in progress_events} == {1, 2}
    assert store.get_run(run_id)["progress"]["worker"] in {1, 2}

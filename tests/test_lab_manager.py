"""RunManager scheduling and state recovery without the large research DB."""

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from radar.lab import manager as manager_module
from radar.lab.manager import RunManager
from radar.strategy.base import StrategyPlugin
from radar.strategy.registry import StrategyRegistration
from radar.strategy.validation import StrategyManifest


class _Strategy(StrategyPlugin):
    def required_features(self) -> set[str]:
        return set()

    def hard_filter(self, context, config):
        return pd.Series(False, index=context.frame.index)

    def score(self, context, config):
        return pd.Series(0.0, index=context.frame.index)

    def select(self, candidates, config):
        return candidates.iloc[0:0].copy()


@pytest.fixture
def manager(tmp_path, monkeypatch):
    root = tmp_path / "project"
    (root / "data").mkdir(parents=True)
    (root / "data" / "phase2-research.duckdb").write_bytes(b"market stub")
    config = root / "config"
    config.mkdir()
    (config / "research.yaml").write_text("fee_profile: test\n", encoding="utf-8")
    (config / "backtest.yaml").write_text("\n".join(
        f"{key}: 1" for key in (
            "initial_capital", "max_new_candidates", "take_profit", "stop_loss",
            "max_holding_sessions", "entry_gap_min", "entry_gap_max",
            "max_position_fraction", "minimum_position_fraction",
            "max_order_to_avg_dollar_volume",
        )
    ), encoding="utf-8")
    for relative in (
        "src/radar/backtest/engine.py", "src/radar/strategy/adapter.py",
        "src/radar/strategy/full_strategy2.py",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# frozen source\n", encoding="utf-8")
    strategy_path = root / "strategies" / "tiny_strategy"
    strategy_path.mkdir(parents=True)
    (strategy_path / "strategy.py").write_text("# strategy source\n", encoding="utf-8")
    manifest = StrategyManifest.model_validate({
        "name": "Tiny Strategy", "id": "tiny_strategy", "version": "1.0.0",
        "interface_version": 1, "author": {"type": "ai", "name": "Test"},
        "description": "Test fixture", "required_features": [],
    })
    registration = StrategyRegistration(
        manifest, {"selection": {"max_candidates": 3}}, _Strategy(), strategy_path,
    )

    def discover(self):
        self.registry.register(registration)

    monkeypatch.setattr(RunManager, "_discover_plugins", discover)
    monkeypatch.setattr(manager_module, "split_dates", lambda *_: {
        name: tuple(pd.Timestamp(day) for day in ("2025-01-02", "2025-01-03", "2025-01-04"))
        for name in ("train", "validation", "test")
    })
    monkeypatch.setattr(manager_module, "load_fee_config",
                        lambda *_: SimpleNamespace(profile="test"))
    monkeypatch.setattr(manager_module, "source_watermark", lambda *_: "watermark")
    monkeypatch.setattr(RunManager, "_data_snapshot", lambda self: "snapshot-hash")
    monkeypatch.setattr(RunManager, "_git_revision", lambda self: "revision")
    monkeypatch.setattr(RunManager, "_git_dirty", lambda self: False)
    monkeypatch.setattr(RunManager, "_worker_pid", staticmethod(lambda _run_id: None))
    return RunManager(root, store_path=tmp_path / "runs.sqlite3", max_workers=2)


def test_queue_metadata_and_new_config_create_new_run(manager):
    first = manager.queue_runs(["tiny_strategy"], split="validation")[0]
    second = manager.queue_runs(
        ["tiny_strategy@1.0.0"], split="validation",
        configs_by_strategy={"tiny_strategy@1.0.0": {"selection": {"max_candidates": 1}}},
    )[0]
    assert first != second
    a, b = manager.store.get_run(first), manager.store.get_run(second)
    assert a["status"] == b["status"] == "queued"
    assert a["metadata"]["config_hash"] != b["metadata"]["config_hash"]
    assert a["metadata"]["config"]["selection"]["max_candidates"] == 3
    assert b["metadata"]["config"]["selection"]["max_candidates"] == 1
    for key in ("strategy_id", "strategy_version", "plugin_interface_version",
                "strategy_code_hash", "config_hash", "git_revision", "feature_version",
                "data_snapshot", "source_watermark", "fee_profile", "slippage_bps",
                "execution_policy", "start_date", "end_date", "evaluation_end", "split"):
        assert key in b["metadata"]


def test_max_two_queued_launches_and_rerun_no_duplicates(manager, monkeypatch):
    run_ids = manager.queue_runs(["tiny_strategy"] * 3)
    launched: list[list[str]] = []

    class FakeProcess:
        def __init__(self, command, **_kwargs):
            launched.append(command)
            self.pid = 1000 + len(launched)

        def poll(self):
            return None

    monkeypatch.setattr(manager_module.subprocess, "Popen", FakeProcess)
    manager.launch_queued()
    manager.launch_queued()
    assert len(launched) == 2
    assert len(manager._processes) == 2
    assert len(manager.store.list_runs(status="queued")) == 3
    assert all(any(run_id in command for command in launched) for run_id in manager._processes)
    remaining = (set(run_ids) - set(manager._processes)).pop()
    assert manager.store.get_run(remaining)["status"] == "queued"


def test_recovery_uses_worker_pid_after_manager_restarts(manager, monkeypatch):
    run_id = manager.queue_runs(["tiny_strategy"])[0]
    manager.store.start_run(run_id, 1234)

    class WorkerProcess:
        def cmdline(self):
            return ["python.exe", "-m", "radar.lab.worker", "--run", run_id]

    monkeypatch.setattr(manager_module.psutil, "Process", lambda pid: WorkerProcess())
    recovered = RunManager(manager.root, store_path=manager.store.path)
    recovered.refresh()
    assert recovered.store.get_run(run_id)["status"] == "running"
    monkeypatch.setattr(manager_module.psutil, "Process",
                        lambda pid: (_ for _ in ()).throw(manager_module.psutil.NoSuchProcess(pid)))
    recovered.refresh()
    assert recovered.store.get_run(run_id)["status"] == "failed"


def test_cancel_and_crash_are_isolated(manager, monkeypatch):
    first, second, third = manager.queue_runs(["tiny_strategy"] * 3)
    for index, run_id in enumerate((first, second, third), 1):
        manager.store.start_run(run_id, 2000 + index)
    manager.cancel(first)
    assert manager.store.get_run(first)["status"] == "cancel_requested"
    monkeypatch.setattr(RunManager, "_process_matches",
                        staticmethod(lambda _pid, run_id: run_id == second))
    manager.refresh()
    assert manager.store.get_run(first)["status"] == "cancelled"
    assert manager.store.get_run(second)["status"] == "running"
    assert manager.store.get_run(third)["status"] == "failed"

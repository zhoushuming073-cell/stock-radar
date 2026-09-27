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
        f"{key}: {value}" for key, value in {
            "initial_capital": 1000000, "max_new_candidates": 3,
            "take_profit": 0.05, "stop_loss": -0.10,
            "max_holding_sessions": 10, "entry_gap_min": -0.10,
            "entry_gap_max": 0.05, "max_position_fraction": 0.3333333333,
            "minimum_position_fraction": 0.01,
            "max_order_to_avg_dollar_volume": 0.02,
        }.items()
    ), encoding="utf-8")
    for relative in (
        "src/radar/backtest/engine.py", "src/radar/strategy/adapter.py",
        "src/radar/strategy/full_strategy2.py",
        "src/radar/lab/worker.py", "src/radar/lab/data.py",
        "src/radar/lab/parameters.py", "src/radar/lab/universe.py",
        "src/radar/backtest/runner.py", "src/radar/research/pipeline.py",
        "src/radar/strategy/context.py", "src/radar/strategy/validation.py",
        "src/radar/strategy/loader.py",
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


def test_stop_loss_override_changes_only_the_new_run(manager):
    baseline = manager.queue_runs(["tiny_strategy"])[0]
    variant = manager.queue_runs(
        ["tiny_strategy"],
        configs_by_strategy={"tiny_strategy": {
            "selection": {"max_candidates": 3},
            "execution": {"stop_loss": -0.20},
        }},
    )[0]
    original = manager.store.get_run(baseline)["metadata"]["execution_policy"]
    changed = manager.store.get_run(variant)["metadata"]["execution_policy"]
    assert original["stop_loss"] == -0.10
    assert changed == {**original, "stop_loss": -0.20}
    with pytest.raises(ValueError, match="execution.stop_loss"):
        manager.queue_runs(
            ["tiny_strategy"],
            configs_by_strategy={"tiny_strategy": {"execution": {"stop_loss": 0}}},
        )


def test_uninstall_only_imported_strategy_and_keep_run_history(manager):
    with pytest.raises(ValueError, match="built-in"):
        manager.uninstall_strategy("tiny_strategy")

    plugin_path = manager.plugin_dir / "imported_strategy@1.0.0"
    plugin_path.mkdir()
    (plugin_path / "strategy.py").write_text("# imported plugin\n", encoding="utf-8")
    manifest = StrategyManifest.model_validate({
        "name": "Imported Strategy", "id": "imported_strategy", "version": "1.0.0",
        "interface_version": 1, "author": {"type": "ai", "name": "Test"},
        "description": "Test fixture", "required_features": [],
    })
    manager.registry.register(StrategyRegistration(
        manifest, {"selection": {"max_candidates": 3}}, _Strategy(), plugin_path,
    ))
    run_id = manager.queue_runs(["imported_strategy"])[0]
    with pytest.raises(ValueError, match="active run"):
        manager.uninstall_strategy("imported_strategy")
    assert plugin_path.exists()

    manager.store.start_run(run_id, 1234)
    manager.store.finish_run(run_id, {"equity": [], "trades": [],
                                      "orders": [], "events": []}, {})
    assert manager.uninstall_strategy("imported_strategy") == 1
    assert not plugin_path.exists()
    assert manager.store.get_run(run_id)["status"] == "completed"
    with pytest.raises(KeyError):
        manager.registry.get("imported_strategy")


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


def test_timeline_stages_launch_in_order(manager, monkeypatch):
    ids = []
    predecessor = None
    for stage in ("train", "validation", "test"):
        run_id = manager.queue_runs(["tiny_strategy"], split=stage,
                                    batch_id="timeline-1", after_run_id=predecessor,
                                    pace_ms=500)[0]
        ids.append(run_id)
        predecessor = run_id

    launched = []

    class FakeProcess:
        def __init__(self, command, **_kwargs):
            launched.append(command[-1])
            self.pid = 9000 + len(launched)

        def poll(self):
            return None

    monkeypatch.setattr(manager_module.subprocess, "Popen", FakeProcess)
    manager.launch_queued()
    assert launched == ids[:1]
    manager.store.start_run(ids[0], 9001)
    manager.store.finish_run(ids[0], {"equity": [], "trades": [],
                                      "orders": [], "events": []}, {})
    manager.launch_queued()
    assert launched == ids[:2]
    manager.store.cancel_run(ids[1])
    manager.launch_queued()
    assert manager.store.get_run(ids[2])["status"] == "cancelled"


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

"""RunManager scheduling and state recovery without the large research DB."""

from pathlib import Path
from types import SimpleNamespace
from uuid import uuid4

import pandas as pd
import pytest

from radar.lab import manager as manager_module
from radar import local_api
from radar.lab.experiments import queue_experiment
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
        "src/radar/lab/scanner.py", "src/radar/lab/scanner_worker.py",
        "src/radar/lab/terminal.py", "src/radar/lab/readiness.py",
        "src/radar/backtest/runner.py", "src/radar/research/pipeline.py",
        "src/radar/strategy/base.py", "src/radar/strategy/context.py", "src/radar/strategy/validation.py",
        "src/radar/strategy/loader.py",
    ):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("# frozen source\n", encoding="utf-8")
    strategy_path = root / "strategies" / "tiny_strategy"
    strategy_path.mkdir(parents=True)
    (strategy_path / "strategy.py").write_text("# strategy source\n", encoding="utf-8")
    (strategy_path / "manifest.yaml").write_text("# manifest\n", encoding="utf-8")
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


def test_multi_strategy_failure_leaves_no_queued_run(manager):
    with pytest.raises(KeyError):
        manager.queue_runs(["tiny_strategy", "unknown_strategy"])
    assert manager.store.list_runs() == []


def test_scanner_horizon_respects_frozen_evaluation_reservation(manager):
    with pytest.raises(ValueError, match="frozen split evaluation boundary"):
        manager.queue_scanner("tiny_strategy", evaluation_overrides={"horizon_sessions": 11})
    assert manager.store.list_scanner_runs() == []
    run = manager.queue_scanner("tiny_strategy", evaluation_overrides={"horizon_sessions": 10})
    assert manager.store.get_scanner_run(run)["metadata"]["evaluation"]["horizon_sessions"] == 10


def test_scanner_worker_cannot_read_prices_or_sessions_past_frozen_boundary(manager, monkeypatch):
    from radar.lab import scanner_worker as worker
    run = manager.queue_scanner("tiny_strategy")
    registration = manager.registry.get("tiny_strategy")
    original_hash = worker.sha256_file
    monkeypatch.setattr(worker, "sha256_file", lambda path:
        "snapshot-hash" if path == manager.database else original_hash(path))
    monkeypatch.setattr(worker, "source_watermark", lambda *_: "watermark")
    monkeypatch.setattr(worker, "available_features", lambda *_: set())
    monkeypatch.setattr(worker, "load_strategy_directory", lambda *_args, **_kwargs: registration)
    monkeypatch.setattr(worker, "split_dates", lambda *_: {
        "validation": (pd.Timestamp("2025-01-02"), pd.Timestamp("2025-01-03"), pd.Timestamp("2025-01-04")),
        "sessions": pd.date_range("2025-01-02", "2025-01-30")})
    frame = pd.DataFrame({"date": pd.date_range("2025-01-02", "2025-01-03"),
                          "symbol": "AAA", "tradability_pass": True}).set_index(["date", "symbol"], drop=False)
    monkeypatch.setattr(worker, "load_strategy_segment", lambda *_: frame)
    monkeypatch.setattr(worker, "published_session_counts", lambda *_: None)
    consumed = {}
    def bars(_database, _start, end):
        consumed["bar_end"] = end
        return pd.DataFrame()
    def scan(_plugin, _config, _frame, _bars, sessions, *_args, **_kwargs):
        consumed["sessions"] = sessions
        return [], {}
    monkeypatch.setattr(worker, "load_forward_bars", bars)
    monkeypatch.setattr(worker, "scan_frames", scan)
    worker.execute_scanner_run(manager.root, manager.store.path, run)
    assert consumed["bar_end"] == pd.Timestamp("2025-01-04")
    assert consumed["sessions"].max() == pd.Timestamp("2025-01-04")


@pytest.mark.parametrize("kind", ["scanner", "backtest"])
def test_batch_research_mutation_rejects_every_variant(manager, monkeypatch, kind):
    state = {"snapshot": "snapshot-hash", "prepared": 0}
    monkeypatch.setattr(RunManager, "_data_snapshot", lambda self: state["snapshot"])
    method_name = "_prepare_scanner_run" if kind == "scanner" else "_prepare_runs"
    original = getattr(manager, method_name)
    def changed(*args, **kwargs):
        result = original(*args, **kwargs)
        state["prepared"] += 1
        state["snapshot"] = "changed-snapshot"
        return result
    monkeypatch.setattr(manager, method_name, changed)
    with pytest.raises(ValueError, match="(?:snapshot|sources) changed"):
        if kind == "scanner":
            manager.queue_scanner_requests([{"strategy_id": "tiny_strategy"}] * 2)
        else:
            manager.queue_run_requests([{"strategy_ids": ["tiny_strategy"]}] * 2)
    assert manager.store.list_runs() == []
    assert manager.store.list_scanner_runs() == []


def test_source_scanner_same_version_changed_implementation_rejected(manager):
    run_id = manager.queue_scanner("tiny_strategy")
    manager.store.start_scanner_run(run_id, 123)
    manager.store.finish_scanner_run(run_id, [], {})
    strategy = manager.registry.get("tiny_strategy")
    (strategy.path / "strategy.py").write_text("# changed without version bump\n", encoding="utf-8")
    with pytest.raises(ValueError, match="signal-producing implementation"):
        manager.queue_runs(["tiny_strategy"], source_scanner_run_id=run_id)
    assert manager.store.list_runs() == []


def test_queued_scanner_rejects_mutated_pit_source_before_loading_features(manager, monkeypatch):
    import hashlib
    import json
    from radar.lab import scanner_worker as scanner_module
    from radar.lab.worker import sha256_file
    data = manager.root / "data"
    csv = data / "security-master.csv"
    csv.write_text("security_id,symbol,valid_from,valid_to,listing_date,delisting_date,exchange,security_type,eligible\n"
                   "AAA-SEC,AAA,2025-01-02,,,,NYSE,common,true\n")
    path = data / "security-master-manifest.json"
    manifest = {"provider": "fixture", "source_version": "1", "coverage_start": "2025-01-02",
                "coverage_end": "2025-01-04", "coverage_complete": True}
    path.write_text(json.dumps(manifest))
    snapshot = sha256_file(manager.database)
    (data / "security-master-feature-store.json").write_text(json.dumps({
        "master_output_sha256": hashlib.sha256(csv.read_bytes()).hexdigest(),
        "source_database_sha256": snapshot, "research_config_sha256": sha256_file(manager.root / "config/research.yaml"),
        "database_sha256": "unused-before-rejection", "feature_basis": "fixture"}))
    monkeypatch.setattr(RunManager, "_data_snapshot", lambda self: snapshot)
    monkeypatch.setattr(manager_module, "local_readiness", lambda *_: {"research_validity": "synthetic_fixture"})
    run = manager.queue_scanner("tiny_strategy", universe_mode="point_in_time")
    path.write_text(json.dumps({**manifest, "source_version": "2"}))
    registration = manager.registry.get("tiny_strategy")
    monkeypatch.setattr(scanner_module, "source_watermark", lambda *_: "watermark")
    monkeypatch.setattr(scanner_module, "available_features", lambda *_: set())
    monkeypatch.setattr(scanner_module, "load_strategy_directory", lambda *_a, **_kw: registration)
    days = pd.DatetimeIndex(["2025-01-02", "2025-01-03", "2025-01-04"])
    monkeypatch.setattr(scanner_module, "split_dates", lambda *_: {"validation": tuple(days), "sessions": days})
    with pytest.raises(ValueError, match="queued PIT security master changed"):
        scanner_module.execute_scanner_run(manager.root, manager.store.path, run)
    assert manager.store.get_scanner_run(run)["status"] == "failed"
    assert manager.store.get_scanner_candidates(run) == []


def test_timeline_batch_failure_leaves_no_stage(manager):
    ids = [str(uuid4()) for _ in range(3)]
    requests = [{"strategy_ids": ["tiny_strategy"], "split": split,
                 "assigned_ids": [run_id],
                 "after_run_id": ids[index - 1] if index else None}
                for index, (split, run_id) in enumerate(zip(
                    ("train", "validation", "test"), ids))]
    requests[1]["strategy_ids"] = ["unknown_strategy"]
    with pytest.raises(KeyError):
        manager.queue_run_requests(requests)
    assert manager.store.list_runs() == []
    requests[1]["strategy_ids"] = ["tiny_strategy"]
    assert manager.queue_run_requests(requests) == ids
    assert [run["run_id"] for run in reversed(manager.store.list_runs())] == ids


def test_walk_forward_real_manager_path(manager, monkeypatch):
    days = pd.date_range("2025-01-02", periods=12, freq="B")
    monkeypatch.setattr(manager_module, "split_dates", lambda *_: {
        "sessions": days, "test_start": days[10],
        "train": tuple(days[:3]), "validation": tuple(days[3:6]),
        "test": tuple(days[10:]),
    })
    window = tuple(str(day.date()) for day in days[6:9])
    run_id = manager.queue_runs(["tiny_strategy"], split="walk_forward",
                                window_override=window)[0]
    assert manager.store.get_run(run_id)["metadata"]["split"] == "walk_forward"


def test_experiment_later_invalid_variant_leaves_no_run(manager):
    with pytest.raises(ValueError, match="unknown strategy override paths"):
        queue_experiment(manager, kind="grid", strategy_id="tiny_strategy",
                         grid={"selection.max_candidates": [1, {"bad": 1}]})
    assert manager.store.list_runs() == []


def test_exact_strategy_versions_have_distinct_schemas_and_runs(manager, monkeypatch):
    first = manager.registry.get("tiny_strategy", "1.0.0")
    for version, elasticity in (("1.0.0", 1), ("2.0.0", 8)):
        path = manager.root / "strategies" / f"full_strategy2_v1_{version}"
        path.mkdir()
        (path / "strategy.py").write_text(f"# version {version}\n", encoding="utf-8")
        manifest = first.manifest.model_copy(update={
            "id": "full_strategy2_v1", "version": version})
        manager.registry.register(StrategyRegistration(
            manifest, {"min_elasticity": elasticity}, _Strategy(), path))
    monkeypatch.setattr(local_api, "lab_manager", lambda: manager)
    monkeypatch.setattr(local_api, "ROOT", manager.root)
    schema_v1 = local_api.lab_parameter_schema("full_strategy2_v1@1.0.0")
    schema_v2 = local_api.lab_parameter_schema("full_strategy2_v1@2.0.0")
    field = "strategy.min_elasticity"
    assert next(item for item in schema_v1 if item["path"] == field)["default"] == 1
    assert next(item for item in schema_v2 if item["path"] == field)["default"] == 8
    ids = manager.queue_runs(["full_strategy2_v1@1.0.0", "full_strategy2_v1@2.0.0"])
    assert [manager.store.get_run(run_id)["metadata"]["strategy_version"]
            for run_id in ids] == ["1.0.0", "2.0.0"]
    assert manager.store.get_run(ids[0])["metadata"]["strategy_code_hash"] != (
        manager.store.get_run(ids[1])["metadata"]["strategy_code_hash"])


def test_uninstall_one_imported_version_with_builtin_same_id(manager, monkeypatch):
    builtin = manager.registry.get("tiny_strategy", "1.0.0")
    imported = manager.plugin_dir / "tiny_strategy@2.0.0"
    imported.mkdir(parents=True)
    (imported / "strategy.py").write_text("# imported v2\n", encoding="utf-8")
    manifest = builtin.manifest.model_copy(update={"version": "2.0.0"})
    manager.registry.register(StrategyRegistration(manifest, builtin.config, _Strategy(), imported))
    monkeypatch.setattr(local_api, "lab_manager", lambda: manager)
    displayed = {item["strategy_ref"]: item for item in local_api.lab_strategies()}
    assert displayed["tiny_strategy@1.0.0"]["removable"] is False
    assert displayed["tiny_strategy@2.0.0"]["removable"] is True
    manager.queue_runs(["tiny_strategy@1.0.0"])
    assert manager.uninstall_strategy("tiny_strategy@2.0.0") == 1
    assert not imported.exists()
    assert manager.registry.get("tiny_strategy", "1.0.0") is builtin


def test_canonical_clone_settings_round_trip(manager):
    reference = "tiny_strategy@1.0.0"
    override = {"exit": {"stop_loss": -0.2},
                "sizing": {"method": "strategy_score"},
                "market_guard": {"mode": "spy_ma200"},
                "execution_timing": "legacy_close"}
    original_id = manager.queue_runs([reference], slippage_bps=25,
                                     execution_overrides=override)[0]
    original = manager.store.get_run(original_id)["metadata"]
    execution = original["resolved_config"]["values"]["execution"]
    cloned_id = manager.queue_runs(
        [reference], split=original["split"], slippage_bps=execution["slippage_bps"],
        configs_by_strategy={reference: original["config"]},
        execution_overrides=execution)[0]
    cloned = manager.store.get_run(cloned_id)["metadata"]
    assert cloned["strategy_version"] == original["strategy_version"]
    assert cloned["strategy_code_hash"] == original["strategy_code_hash"]
    assert cloned["resolved_config"]["values"] == original["resolved_config"]["values"]


def test_fresh_oos_queues_both_run_types_only_when_available(manager, monkeypatch):
    with pytest.raises(ValueError, match="not available"):
        manager.queue_runs(["tiny_strategy"], split="fresh_oos")
    with pytest.raises(ValueError, match="not available"):
        manager.queue_scanner("tiny_strategy", split="fresh_oos")
    days = pd.date_range("2025-01-02", periods=15, freq="B")
    monkeypatch.setattr(manager_module, "split_dates", lambda *_: {
        "sessions": days, "test_start": days[9],
        "train": tuple(days[:3]), "validation": tuple(days[3:6]),
        "test": tuple(days[9:12]), "fresh_oos": tuple(days[12:15]),
    })
    backtest = manager.queue_runs(["tiny_strategy"], split="fresh_oos")[0]
    scanner = manager.queue_scanner("tiny_strategy", split="fresh_oos")
    assert manager.store.get_run(backtest)["metadata"]["split"] == "fresh_oos"
    assert manager.store.get_scanner_run(scanner)["metadata"]["split"] == "fresh_oos"


def test_scanner_variant_batch_failure_leaves_no_run(manager):
    requests = [{"strategy_id": "tiny_strategy", "split": "validation"},
                {"strategy_id": "tiny_strategy", "split": "validation",
                 "config_override": {"selection": {"max_candidates": 3}, "unknown": 1}}]
    with pytest.raises(ValueError, match="unknown strategy override paths"):
        manager.queue_scanner_requests(requests)
    assert manager.store.list_scanner_runs() == []


def test_queue_metadata_and_new_config_create_new_run(manager):
    first = manager.queue_runs(["tiny_strategy"], split="validation")[0]
    second = manager.queue_runs(
        ["tiny_strategy@1.0.0"], split="validation",
        configs_by_strategy={"tiny_strategy@1.0.0": {"selection": {"max_candidates": 1}}},
    )[0]
    assert first != second
    a, b = manager.store.get_run(first), manager.store.get_run(second)
    assert a["status"] == b["status"] == "queued"
    assert a["metadata"]["execution_policy"]["execution_timing"] == "next_open"
    assert a["metadata"]["config_hash"] != b["metadata"]["config_hash"]
    assert a["metadata"]["config"]["selection"]["max_candidates"] == 3
    assert b["metadata"]["config"]["selection"]["max_candidates"] == 1
    assert a["metadata"]["market_feature_version"] == manager_module.MARKET_FEATURE_VERSION
    assert a["metadata"]["resolved_config"]["values"]["dataset"]["market_feature_version"] == manager_module.MARKET_FEATURE_VERSION
    for key in ("strategy_id", "strategy_version", "plugin_interface_version",
                "strategy_code_hash", "config_hash", "git_revision", "feature_version",
                "data_snapshot", "source_watermark", "fee_profile", "slippage_bps",
                "execution_policy", "start_date", "end_date", "evaluation_end", "split"):
        assert key in b["metadata"]


def test_git_metadata_probes_do_not_open_console(tmp_path, monkeypatch):
    calls = []

    def fake_run(command, **options):
        calls.append((command, options))
        return SimpleNamespace(returncode=0, stdout="revision\n")

    monkeypatch.setattr(manager_module.subprocess, "run", fake_run)
    probe = SimpleNamespace(root=tmp_path)
    assert RunManager._git_revision(probe) == "revision"
    assert RunManager._git_dirty(probe) is True
    assert [command[1] for command, _ in calls] == ["rev-parse", "status"]
    assert all(options["creationflags"] == getattr(manager_module.subprocess, "CREATE_NO_WINDOW", 0)
               for _, options in calls)


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
    with pytest.raises(ValueError, match="strategy_id@version"):
        manager.uninstall_strategy("tiny_strategy")
    with pytest.raises(ValueError, match="built-in"):
        manager.uninstall_strategy("tiny_strategy@1.0.0")

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
        manager.uninstall_strategy("imported_strategy@1.0.0")
    assert plugin_path.exists()

    manager.store.start_run(run_id, 1234)
    manager.store.finish_run(run_id, {"equity": [], "trades": [],
                                      "orders": [], "events": []}, {})
    assert manager.uninstall_strategy("imported_strategy@1.0.0") == 1
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


def test_scanner_and_backtest_share_one_worker_budget(manager, monkeypatch):
    backtests = manager.queue_runs(["tiny_strategy"] * 2)
    required = {key: "fixture" for key in (
        "strategy_id", "strategy_version", "plugin_interface_version", "config",
        "selection", "evaluation", "feature_version", "market_feature_version",
        "data_snapshot", "source_watermark", "git_revision", "signal_start",
        "signal_end", "label_version", "strategy_code_hash", "config_hash")}
    required["config"] = {}
    required["selection"] = {}
    required["evaluation"] = {}
    scanner = manager.store.create_scanner_run(required)
    launched = []

    class FakeProcess:
        def __init__(self, command, **_kwargs):
            launched.append(command)

        def poll(self):
            return None

    monkeypatch.setattr(manager_module.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(RunManager, "_scanner_worker_pid", staticmethod(lambda _id: None))
    manager.launch_queued_scanners()
    manager.launch_queued()
    assert len(launched) == 2
    assert all("radar.lab.worker" in command for command in launched)
    assert len(manager.store.list_runs(status="queued")) == 2
    assert manager.store.get_scanner_run(scanner)["status"] == "queued"
    assert [next(run_id for run_id in backtests if run_id in command)
            for command in launched] == backtests


def test_global_scheduler_uses_oldest_pending_across_run_types(manager, monkeypatch):
    manager.max_workers = 1
    first = manager.queue_runs(["tiny_strategy"])[0]
    required = {key: "fixture" for key in (
        "strategy_id", "strategy_version", "plugin_interface_version", "config",
        "selection", "evaluation", "feature_version", "market_feature_version",
        "data_snapshot", "source_watermark", "git_revision", "signal_start",
        "signal_end", "label_version", "strategy_code_hash", "config_hash")}
    required.update(config={}, selection={}, evaluation={})
    scanner = manager.store.create_scanner_run(required)
    last = manager.queue_runs(["tiny_strategy"])[0]
    launched = []
    class FakeProcess:
        def __init__(self, command, **_kwargs):
            launched.append(command)
            self.pid = 1000 + len(launched)
        def poll(self):
            return None
    monkeypatch.setattr(manager_module.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(RunManager, "_scanner_worker_pid", staticmethod(lambda _id: None))
    manager.launch_queued()
    assert first in launched[0]
    manager.store.start_run(first, 1001)
    manager.store.finish_run(first, {"equity": [], "trades": [],
                                    "orders": [], "events": []}, {})
    manager.launch_queued()
    assert scanner in launched[1]
    assert "radar.lab.scanner_worker" in launched[1]
    assert last not in launched[1]


def test_restarted_scheduler_keeps_cross_type_queue_order(manager, monkeypatch):
    required = {key: "fixture" for key in (
        "strategy_id", "strategy_version", "plugin_interface_version", "config",
        "selection", "evaluation", "feature_version", "market_feature_version",
        "data_snapshot", "source_watermark", "git_revision", "signal_start",
        "signal_end", "label_version", "strategy_code_hash", "config_hash")}
    required.update(config={}, selection={}, evaluation={})
    scanner = manager.store.create_scanner_run(required)
    manager.queue_runs(["tiny_strategy"])
    launched = []
    class FakeProcess:
        def __init__(self, command, **_kwargs):
            launched.append(command)
        def poll(self):
            return None
    monkeypatch.setattr(manager_module.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(RunManager, "_scanner_worker_pid", staticmethod(lambda _id: None))
    recovered = RunManager(manager.root, store_path=manager.store.path, max_workers=1)
    recovered.launch_queued()
    assert len(launched) == 1
    assert scanner in launched[0]


def test_restarted_manager_counts_existing_scanner_worker(manager, monkeypatch):
    backtests = manager.queue_runs(["tiny_strategy"] * 2)
    fields = {key: "fixture" for key in (
        "strategy_id", "strategy_version", "plugin_interface_version", "config",
        "selection", "evaluation", "feature_version", "market_feature_version",
        "data_snapshot", "source_watermark", "git_revision", "signal_start",
        "signal_end", "label_version", "strategy_code_hash", "config_hash")}
    fields.update(config={}, selection={}, evaluation={})
    scanner = manager.store.create_scanner_run(fields)
    launched = []

    class FakeProcess:
        def __init__(self, command, **_kwargs):
            launched.append(command)

        def poll(self):
            return None

    monkeypatch.setattr(manager_module.subprocess, "Popen", FakeProcess)
    monkeypatch.setattr(RunManager, "_scanner_worker_pid",
                        staticmethod(lambda run_id: 4321 if run_id == scanner else None))
    recovered = RunManager(manager.root, store_path=manager.store.path, max_workers=2)
    recovered.launch_queued()
    assert len(launched) == 1
    assert sum(run_id in launched[0] for run_id in backtests) == 1


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

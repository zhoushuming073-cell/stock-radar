from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pandas as pd
import pytest

from radar.lab import experiments


class FakeManager:
    def __init__(self) -> None:
        self.registry = SimpleNamespace(get=lambda strategy_id: SimpleNamespace(
            config={"min_elasticity": 76.0, "max_new": 3}))
        self.calls = []
        self.database = Path("market.duckdb")
        self.root = Path(".")

    def queue_runs(self, ids, **kwargs):
        self.calls.append((ids, kwargs))
        return [f"run-{len(self.calls)}"]

    def launch_queued(self):
        pass

    def queue_scanner(self, strategy_id, **kwargs):
        self.calls.append((strategy_id, kwargs))
        return f"scanner-{len(self.calls)}"

    def launch_queued_scanners(self):
        pass


def test_grid_is_bounded_and_keeps_test_out() -> None:
    manager = FakeManager()
    with pytest.raises(ValueError, match="Train and Validation"):
        experiments.queue_experiment(manager, kind="grid", strategy_id="full_strategy2_v1",
                                     split="test", grid={"min_elasticity": [70, 75]})
    result = experiments.queue_experiment(manager, kind="grid",
                                          strategy_id="full_strategy2_v1",
                                          grid={"min_elasticity": [70, 75, 80]})
    assert result["count"] == 3
    assert [call[1]["configs_by_strategy"]["full_strategy2_v1"]["min_elasticity"]
            for call in manager.calls] == [70, 75, 80]


def test_grid_updates_nested_parameter_without_changing_siblings() -> None:
    manager = FakeManager()
    manager.registry = SimpleNamespace(get=lambda strategy_id: SimpleNamespace(
        config={"pullback": {"min_depth": 0.1, "max_depth": 0.3}}))
    result = experiments.queue_experiment(
        manager, kind="grid", strategy_id="nested_strategy",
        grid={"pullback.min_depth": [0.12, 0.18]},
    )
    assert result["count"] == 2
    assert [call[1]["configs_by_strategy"]["nested_strategy"]["pullback"]
            for call in manager.calls] == [
                {"min_depth": 0.12, "max_depth": 0.3},
                {"min_depth": 0.18, "max_depth": 0.3},
            ]


def test_scanner_grid_can_vary_evaluation_namespace() -> None:
    manager = FakeManager()
    result = experiments.queue_experiment(
        manager, kind="grid", run_type="scanner", strategy_id="full_strategy2_v1",
        grid={"evaluation.event_cooldown_sessions": [0, 5]},
    )
    assert result["run_type"] == "scanner"
    assert result["count"] == 2
    assert [call[1]["evaluation_overrides"]["event_cooldown_sessions"]
            for call in manager.calls] == [0, 5]
    assert all(call[1]["experiment"]["run_type"] == "scanner"
               for call in manager.calls)
    nested = FakeManager()
    experiments.queue_experiment(
        nested, kind="grid", run_type="scanner", strategy_id="full_strategy2_v1",
        grid={"evaluation.false_falling_knife.max_drawdown_threshold": [-.08, -.10]},
    )
    assert nested.calls[1][1]["evaluation_overrides"] == {
        "false_falling_knife": {"max_drawdown_threshold": -.10}}
    with pytest.raises(ValueError, match="invalid grid parameter"):
        experiments.queue_experiment(
            FakeManager(), kind="grid", run_type="backtest",
            strategy_id="full_strategy2_v1",
            grid={"evaluation.event_cooldown_sessions": [0, 5]},
        )


def test_scanner_experiment_summary_uses_event_metrics() -> None:
    scanner_runs = [{"run_id": "scan-1", "status": "completed",
                     "metadata": {"strategy_id": "full_strategy2_v1",
                                  "evaluation": {"top_k_values": [5, 10]},
                                  "experiment": {"id": "exp-1", "kind": "grid",
                                                 "run_type": "scanner", "index": 0,
                                                 "variant": {"evaluation.event_cooldown_sessions": 5}}},
                     "metrics": {"event_precision_at_10": .5,
                                 "event_lift_at_10": 1.25,
                                 "event_top_10_count": 12}}]
    summary = experiments.summarize_experiments([], scanner_runs)[0]
    assert summary["run_type"] == "scanner"
    assert summary["median_precision"] == .5
    assert summary["runs"][0]["lift"] == 1.25
    second = {**scanner_runs[0], "run_id": "scan-2",
              "metadata": {**scanner_runs[0]["metadata"],
                           "evaluation": {"top_k_values": [5]},
                           "experiment": {**scanner_runs[0]["metadata"]["experiment"],
                                          "index": 1}},
              "metrics": {"event_precision_at_5": .8, "event_lift_at_5": 1.6,
                          "event_top_5_count": 7}}
    varied = experiments.summarize_experiments([], [*scanner_runs, second])[0]
    assert varied["top_k"] == 5
    assert varied["runs"][0]["top_k"] == 5
    third = {**second, "run_id": "scan-3",
             "metadata": {**second["metadata"], "evaluation": {"top_k_values": [20]},
                          "experiment": {**second["metadata"]["experiment"],
                                         "index": 2}},
             "metrics": {"event_precision_at_20": .6}}
    incomparable = experiments.summarize_experiments([], [*scanner_runs, third])[0]
    assert incomparable["top_k"] is None
    assert incomparable["median_precision"] is None


def test_ablation_creates_full_baseline_and_each_stage() -> None:
    manager = FakeManager()
    result = experiments.queue_experiment(manager, kind="ablation",
                                          strategy_id="full_strategy2_v1")
    assert result["count"] == 9
    disabled = [call[1]["configs_by_strategy"]["full_strategy2_v1"]["disabled_stages"]
                for call in manager.calls]
    assert disabled[0] == []
    assert {item[0] for item in disabled[1:]} == set(experiments.ABLATION_STAGES)


def test_walk_forward_folds_never_reach_reserved_test(monkeypatch) -> None:
    manager = FakeManager()
    sessions = pd.bdate_range("2020-01-01", periods=950)
    test_start = sessions[850]
    monkeypatch.setattr(experiments, "split_dates", lambda *_: {
        "sessions": sessions, "test_start": test_start})
    result = experiments.queue_experiment(manager, kind="walk_forward",
                                          strategy_id="full_strategy2_v1")
    assert result["count"] >= 2
    for _, kwargs in manager.calls:
        assert kwargs["split"] == "walk_forward"
        assert kwargs["window_override"][2] < str(test_start.date())
        assert kwargs["experiment"]["variant"]["train"][1] < kwargs["window_override"][0]

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

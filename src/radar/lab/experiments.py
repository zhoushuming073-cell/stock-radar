"""Bounded research experiments using the authoritative backtest worker."""

from __future__ import annotations

from itertools import product
from statistics import median
from typing import Any
from uuid import uuid4

from radar.backtest.runner import split_dates
from radar.lab.manager import RunManager, _plain


ABLATION_STAGES = (
    "prior_strength", "pullback_quality", "exhaustion",
    "support_absorption", "new_low_stop", "early_reversal",
    "not_extended", "elasticity",
)


def _registration(manager: RunManager, strategy_id: str):
    return manager.registry.get(strategy_id)


def queue_experiment(
    manager: RunManager, *, kind: str, strategy_id: str,
    split: str = "validation", grid: dict[str, list[Any]] | None = None,
    slippage_bps: float = 10.0,
) -> dict:
    if split not in {"train", "validation"}:
        raise ValueError("experiments are limited to Train and Validation")
    registration = _registration(manager, strategy_id)
    base = _plain(registration.config)
    experiment_id = str(uuid4())
    queued: list[str] = []
    if kind == "grid":
        if not grid or not isinstance(grid, dict) or len(grid) > 4:
            raise ValueError("grid requires 1 to 4 parameter lists")
        for name, values in grid.items():
            if name not in base or not isinstance(values, list) or not 1 <= len(values) <= 12:
                raise ValueError(f"invalid grid parameter: {name}")
        combinations = list(product(*grid.values()))
        if len(combinations) > 64:
            raise ValueError("grid is limited to 64 variants")
        for index, values in enumerate(combinations):
            variant = dict(zip(grid, values))
            config = {**base, **variant}
            queued.extend(manager.queue_runs(
                [strategy_id], split=split, slippage_bps=slippage_bps,
                configs_by_strategy={strategy_id: config},
                experiment={"id": experiment_id, "kind": kind,
                            "variant": variant, "index": index},
            ))
    elif kind == "ablation":
        if strategy_id != "full_strategy2_v1":
            raise ValueError("Stage ablation is available for full_strategy2_v1")
        for index, stage in enumerate((None, *ABLATION_STAGES)):
            config = {**base, "disabled_stages": [stage] if stage else []}
            queued.extend(manager.queue_runs(
                [strategy_id], split=split, slippage_bps=slippage_bps,
                configs_by_strategy={strategy_id: config},
                experiment={"id": experiment_id, "kind": kind,
                            "variant": stage or "full", "index": index},
            ))
    elif kind == "walk_forward":
        dates = split_dates(manager.database, manager.root / "config" / "research.yaml")
        sessions = dates["sessions"]
        limit = next(i for i, day in enumerate(sessions) if day == dates["test_start"])
        train, validation, oos, embargo, step = 504, 126, 63, 10, 63
        index = 0
        for start in range(0, limit - train - validation - oos - embargo + 1, step):
            signal_start = start + train + validation
            signal_end = signal_start + oos - 1
            evaluation_end = signal_end + embargo
            window = tuple(str(sessions[i].date()) for i in
                           (signal_start, signal_end, evaluation_end))
            fold = {
                "train": [str(sessions[start].date()), str(sessions[start + train - 1].date())],
                "validation": [str(sessions[start + train].date()),
                               str(sessions[signal_start - 1].date())],
                "oos": [window[0], window[1]],
                "index": index,
            }
            queued.extend(manager.queue_runs(
                [strategy_id], split="walk_forward", window_override=window,
                slippage_bps=slippage_bps,
                configs_by_strategy={strategy_id: base},
                experiment={"id": experiment_id, "kind": kind,
                            "variant": fold, "index": index},
            ))
            index += 1
        if not queued:
            raise ValueError("not enough pre-Test history for a walk-forward fold")
    else:
        raise ValueError("unknown experiment type")
    manager.launch_queued()
    return {"experiment_id": experiment_id, "run_ids": queued,
            "kind": kind, "count": len(queued)}


def summarize_experiments(runs: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for run in runs:
        experiment = run.get("metadata", {}).get("experiment")
        if experiment:
            groups.setdefault(experiment["id"], []).append(run)
    summaries = []
    for experiment_id, group in groups.items():
        group.sort(key=lambda run: run["metadata"]["experiment"]["index"])
        completed = [run for run in group if run["status"] == "completed"]
        returns = [run["metrics"]["total_return"] for run in completed]
        drawdowns = [run["metrics"]["max_drawdown"] for run in completed]
        summaries.append({
            "id": experiment_id,
            "kind": group[0]["metadata"]["experiment"]["kind"],
            "strategy_id": group[0]["metadata"]["strategy_id"],
            "total": len(group), "completed": len(completed),
            "positive": sum(value > 0 for value in returns),
            "median_return": median(returns) if returns else None,
            "mean_return": sum(returns) / len(returns) if returns else None,
            "worst_return": min(returns) if returns else None,
            "best_return": max(returns) if returns else None,
            "median_drawdown": median(drawdowns) if drawdowns else None,
            "parameter_selection_consistency": (
                "fixed parameters across folds" if group[0]["metadata"]["experiment"]["kind"]
                == "walk_forward" else None
            ),
            "runs": [{"run_id": run["run_id"], "status": run["status"],
                      "variant": run["metadata"]["experiment"]["variant"],
                      "total_return": (run.get("metrics") or {}).get("total_return"),
                      "max_drawdown": (run.get("metrics") or {}).get("max_drawdown")}
                     for run in group],
        })
    return summaries

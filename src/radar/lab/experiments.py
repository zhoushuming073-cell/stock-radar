"""Bounded Scanner and Backtest research experiments."""

from __future__ import annotations

import json
from itertools import product
from statistics import median
from typing import Any
from uuid import uuid4

from radar.backtest.runner import split_dates
from radar.lab.manager import RunManager, _plain
from radar.lab.scanner import evaluation_settings


ABLATION_STAGES = (
    "prior_strength", "pullback_quality", "exhaustion",
    "support_absorption", "new_low_stop", "early_reversal",
    "not_extended", "elasticity",
)


def _resolve_leaf(base: dict, dotted: str) -> bool:
    """True when a (possibly dotted) parameter path exists in the config."""
    node = base
    parts = dotted.split(".")
    for part in parts[:-1]:
        if not isinstance(node, dict) or part not in node:
            return False
        node = node[part]
    return isinstance(node, dict) and parts[-1] in node


def _apply_variant(base: dict, variant: dict) -> dict:
    """Copy the base config and set each (possibly dotted) variant value."""
    config = _plain(base)
    for name, value in variant.items():
        parts = name.split(".")
        node = config
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value
    return config


def _registration(manager: RunManager, strategy_id: str):
    if "@" in strategy_id:
        identifier, version = strategy_id.rsplit("@", 1)
        return manager.registry.get(identifier, version)
    return manager.registry.get(strategy_id)


def queue_experiment(
    manager: RunManager, *, kind: str, strategy_id: str,
    split: str = "validation", grid: dict[str, list[Any]] | None = None,
    slippage_bps: float = 10.0,
    run_type: str = "backtest", config_override: dict | None = None,
    evaluation_overrides: dict | None = None,
    execution_overrides: dict | None = None,
    universe_mode: str = "current_snapshot",
    engine: str | None = None,
) -> dict:
    if split not in {"train", "validation"}:
        raise ValueError("experiments are limited to Train and Validation")
    if run_type not in {"backtest", "scanner"}:
        raise ValueError("experiment run_type must be backtest or scanner")
    registration = _registration(manager, strategy_id)
    base = _plain(config_override if config_override is not None else registration.config)
    evaluation_base = evaluation_settings(evaluation_overrides) if run_type == "scanner" else None
    evaluation_draft = _plain(evaluation_overrides or {})
    experiment_id = str(uuid4())
    requests: list[dict[str, Any]] = []
    def queue_variant(config: dict, evaluation: dict | None, variant: Any, index: int) -> None:
        metadata = {"id": experiment_id, "kind": kind, "run_type": run_type,
                    "variant": variant, "index": index}
        if run_type == "scanner":
            requests.append({"strategy_id": strategy_id, "split": split,
                             "config_override": config, "evaluation_overrides": evaluation,
                             "universe_mode": universe_mode, "experiment": metadata})
        else:
            requests.append({"strategy_ids": [strategy_id], "split": split,
                             "slippage_bps": slippage_bps,
                             "configs_by_strategy": {strategy_id: config},
                             "execution_overrides": execution_overrides,
                             "universe_mode": universe_mode, "experiment": metadata})
    if kind == "grid":
        if not grid or not isinstance(grid, dict) or len(grid) > 4:
            raise ValueError("grid requires 1 to 4 parameter lists")
        for name, values in grid.items():
            namespace, _, path = name.partition(".")
            source = evaluation_base if namespace == "evaluation" else base
            field = path if namespace in {"strategy", "evaluation"} else name
            if (namespace == "evaluation" and run_type != "scanner" or
                    not _resolve_leaf(source, field) or
                    not isinstance(values, list) or not 1 <= len(values) <= 12):
                raise ValueError(f"invalid grid parameter: {name}")
        combinations = list(product(*grid.values()))
        if len(combinations) > 64:
            raise ValueError("grid is limited to 64 variants")
        prepared = []
        for index, values in enumerate(combinations):
            variant = dict(zip(grid, values))
            strategy_changes = {key.removeprefix("strategy."): value
                                for key, value in variant.items()
                                if not key.startswith("evaluation.")}
            evaluation_changes = {key.removeprefix("evaluation."): value
                                  for key, value in variant.items()
                                  if key.startswith("evaluation.")}
            config = _apply_variant(base, strategy_changes)
            evaluation = (_apply_variant(evaluation_draft, evaluation_changes)
                          if evaluation_base is not None else None)
            if evaluation is not None:
                evaluation_settings(_apply_variant(evaluation_base, evaluation_changes))
            prepared.append((config, evaluation, variant, index))
        for config, evaluation, variant, index in prepared:
            queue_variant(config, evaluation, variant, index)
    elif kind == "ablation":
        if registration.manifest.id != "full_strategy2_v1":
            raise ValueError("Stage ablation is available for full_strategy2_v1")
        for index, stage in enumerate((None, *ABLATION_STAGES)):
            config = {**base, "disabled_stages": [stage] if stage else []}
            queue_variant(config, evaluation_draft if run_type == "scanner" else None,
                          stage or "full", index)
    elif kind == "walk_forward":
        if run_type == "scanner":
            raise ValueError("Scanner experiments support grid and ablation; rolling windows are backtest-only")
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
            requests.append({"strategy_ids": [strategy_id], "split": "walk_forward",
                             "window_override": window, "slippage_bps": slippage_bps,
                             "configs_by_strategy": {strategy_id: base},
                             "execution_overrides": execution_overrides,
                             "universe_mode": universe_mode,
                             "experiment": {"id": experiment_id, "kind": kind,
                                            "run_type": run_type, "variant": fold,
                                            "index": index}})
            index += 1
        if not requests:
            raise ValueError("not enough pre-Test history for a walk-forward fold")
    else:
        raise ValueError("unknown experiment type")
    if run_type == 'backtest' and engine is not None:
        for request in requests:
            request['engine'] = engine
    queued = (manager.queue_scanner_requests(requests) if run_type == "scanner"
              else manager.queue_run_requests(requests))
    if run_type == "scanner":
        manager.launch_queued_scanners()
    else:
        manager.launch_queued()
    return {"experiment_id": experiment_id, "run_ids": queued,
            "kind": kind, "run_type": run_type, "count": len(queued)}


def summarize_experiments(runs: list[dict], scanner_runs: list[dict] | None = None) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for run in [*runs, *(scanner_runs or [])]:
        experiment = run.get("metadata", {}).get("experiment")
        if experiment:
            groups.setdefault(experiment["id"], []).append(run)
    summaries = []
    for experiment_id, group in groups.items():
        group.sort(key=lambda run: run["metadata"]["experiment"]["index"])
        completed = [run for run in group if run["status"] == "completed"]
        run_type = group[0]["metadata"]["experiment"].get("run_type", "backtest")
        if run_type == "scanner":
            top_k_sets = [set(run["metadata"].get("evaluation", {}).get(
                "top_k_values", [10])) for run in group]
            common_k = set.intersection(*top_k_sets)
            display_k = (10 if 10 in common_k else min(common_k)) if common_k else None
            scanner_rows = []
            comparison_groups: dict[str, dict] = {}
            for run in group:
                choices = run["metadata"].get("evaluation", {}).get("top_k_values", [10])
                k = display_k if display_k is not None else (10 if 10 in choices else choices[0])
                metrics = run.get("metrics") or {}
                metadata = run["metadata"]
                evaluation = metadata.get("evaluation", {})
                signature = {key: evaluation.get(key) for key in (
                    "horizon_sessions", "success_rule", "primary_target",
                    "primary_adverse_target", "event_cooldown_sessions")}
                signature.update({"top_k": k, "label_version": metadata.get("label_version"),
                                  "feature_version": metadata.get("feature_version"),
                                  "market_feature_version": metadata.get("market_feature_version"),
                                  "data_snapshot": metadata.get("data_snapshot"),
                                  "universe_mode": metadata.get("universe_mode", "current_snapshot")})
                signature_key = json.dumps(signature, sort_keys=True)
                comparison_groups.setdefault(signature_key, {"signature": signature,
                                                             "run_ids": [], "precisions": []})
                comparison_groups[signature_key]["run_ids"].append(run["run_id"])
                precision = metrics.get(f"event_precision_at_{k}")
                if run["status"] == "completed" and precision is not None:
                    comparison_groups[signature_key]["precisions"].append(precision)
                scanner_rows.append({
                    "run_id": run["run_id"], "status": run["status"],
                    "variant": run["metadata"]["experiment"]["variant"],
                    "top_k": k, "precision": precision,
                    "lift": metrics.get(f"event_lift_at_{k}"),
                    "events": metrics.get(f"event_top_{k}_count"),
                    "evaluation_signature": signature,
                })
            precisions = [row["precision"] for row in scanner_rows
                          if row["status"] == "completed" and row["precision"] is not None]
            comparable = len(comparison_groups) == 1
            summaries.append({
                "id": experiment_id, "kind": group[0]["metadata"]["experiment"]["kind"],
                "run_type": run_type, "strategy_id": group[0]["metadata"]["strategy_id"],
                "top_k": display_k if comparable else None,
                "total": len(group), "completed": len(completed),
                "compatible": comparable,
                "comparison_groups": [{"signature": item["signature"],
                                       "run_ids": item["run_ids"],
                                       "median_precision": median(item["precisions"])
                                       if item["precisions"] else None,
                                       "mean_precision": sum(item["precisions"]) / len(item["precisions"])
                                       if item["precisions"] else None}
                                      for item in comparison_groups.values()],
                "median_precision": median(precisions) if comparable and precisions else None,
                "mean_precision": (sum(precisions) / len(precisions)
                                   if comparable and precisions else None),
                "runs": scanner_rows,
            })
            continue
        returns = [run["metrics"]["total_return"] for run in completed]
        drawdowns = [run["metrics"]["max_drawdown"] for run in completed]
        summaries.append({
            "id": experiment_id,
            "kind": group[0]["metadata"]["experiment"]["kind"],
            "run_type": run_type,
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

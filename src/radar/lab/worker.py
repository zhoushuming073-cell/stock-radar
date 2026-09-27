"""One isolated local backtest process per immutable research Run."""

from __future__ import annotations

import argparse
from dataclasses import replace
import hashlib
import os
from pathlib import Path
import time
import traceback
import pandas as pd

from radar.backtest.costs import load_fee_config
from radar.backtest.engine import BacktestCancelled, BacktestConfig, run_backtest
from radar.backtest.metrics import summarize_backtest
from radar.backtest.runner import _engine_config, _rules, load_backtest_config, split_dates
from radar.lab.data import available_features, load_strategy_segment, source_watermark
from radar.lab.execution import resolve_exit_policy
from radar.lab.store import RunStore
from radar.research.pipeline import FEATURE_VERSION
from radar.strategy.adapter import make_candidate_selector
from radar.strategy.loader import load_strategy_directory


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def execute_run(root: Path, store_path: Path, run_id: str) -> dict:
    root = root.resolve()
    store = RunStore(store_path)
    record = store.get_run(run_id)
    metadata = record["metadata"]
    store.start_run(run_id, os.getpid())
    try:
        database = root / "data" / "phase2-research.duckdb"
        backtest_path = root / "config" / "backtest.yaml"
        research_path = root / "config" / "research.yaml"
        strategy_path = Path(metadata["strategy_path"])
        for path, key in ((database, "data_snapshot"),
                          (backtest_path, "backtest_config_hash"),
                          (research_path, "research_config_hash"),
                          (strategy_path / "strategy.py", "strategy_code_hash"),
                          (root / "src" / "radar" / "backtest" / "engine.py", "engine_code_hash"),
                          (root / "src" / "radar" / "strategy" / "adapter.py", "adapter_code_hash"),
                          (root / "src" / "radar" / "strategy" / "full_strategy2.py",
                           "legacy_strategy_code_hash")):
            if sha256_file(path) != metadata[key]:
                raise ValueError(f"run source changed after queuing: {path.name}")
        if metadata["feature_version"] != FEATURE_VERSION:
            raise ValueError("feature version changed after queuing")
        if source_watermark(database) != metadata["source_watermark"]:
            raise ValueError("market source watermark changed after queuing")
        registration = load_strategy_directory(
            strategy_path, available_features(database), run_tests=True,
        )
        manifest = registration.manifest
        if (manifest.id, manifest.version, manifest.interface_version) != (
            metadata["strategy_id"], metadata["strategy_version"],
            metadata["plugin_interface_version"],
        ):
            raise ValueError("strategy identity changed after queuing")
        raw = load_backtest_config(backtest_path)
        exits, source = resolve_exit_policy(raw, metadata["config"])
        if metadata.get("exit_policy_source", source) != source:
            raise ValueError("queued exit policy source changed")
        if any(metadata["execution_policy"].get(key) != value for key, value in exits.items()):
            raise ValueError("queued exits differ from the strategy configuration")
        raw = {**raw, **exits}
        fees = load_fee_config(research_path)
        if fees.profile != metadata["fee_profile"]:
            raise ValueError("fee profile changed after queuing")
        split = split_dates(database, research_path)
        if metadata["split"] == "walk_forward":
            dates = tuple(pd.Timestamp(day) for day in metadata["window"])
            sessions = {str(day.date()) for day in split["sessions"]}
            if not all(day in sessions for day in metadata["window"]):
                raise ValueError("walk-forward dates changed after queuing")
            if metadata["window"][2] >= str(split["test_start"].date()):
                raise ValueError("walk-forward window includes Test")
        else:
            dates = split[metadata["split"]]
            if [str(day.date()) for day in dates] != metadata["window"]:
                raise ValueError("split dates changed after queuing")
        frame = load_strategy_segment(database, dates[0], dates[2],
                                      set(manifest.required_features))
        config = _engine_config(
            raw, variant="full_strategy2", allocator="equal_cash",
            slippage_bps=float(metadata["slippage_bps"]),
            max_position_fraction=float(raw["max_position_fraction"]),
        )
        if isinstance(config, BacktestConfig):
            config = replace(config, execution_timing=metadata["execution_policy"].get(
                "execution_timing", "legacy_close"))
        selector = make_candidate_selector(
            registration.plugin, metadata["config"],
            max_new=int(raw["max_new_candidates"]),
        )
        pace_ms = int(metadata.get("pace_ms", 0))
        if not 0 <= pace_ms <= 2000:
            raise ValueError("invalid timeline pace")

        def report_progress(snapshot: dict) -> None:
            store.append_progress(run_id, snapshot)
            if pace_ms:
                time.sleep(pace_ms / 1000)

        result = run_backtest(
            frame, split["sessions"], signal_start=dates[0],
            signal_end=dates[1], evaluation_end=dates[2],
            rules=_rules(raw), fee_config=fees, config=config,
            candidate_selector=selector,
            progress_callback=report_progress,
            cancel_requested=lambda: store.get_run(run_id)["cancel_requested"],
        )
        metrics = summarize_backtest(result.equity, result.trades,
                                     config.initial_capital)
        if store.get_run(run_id)["cancel_requested"]:
            store.cancel_run(run_id)
            return {"status": "cancelled"}
        store.finish_run(run_id, result, metrics)
        return metrics
    except BacktestCancelled:
        store.cancel_run(run_id)
        return {"status": "cancelled"}
    except Exception as exc:
        store.fail_run(run_id, f"{type(exc).__name__}: {exc}")
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    try:
        execute_run(args.root, args.store, args.run)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)


if __name__ == "__main__":
    main()

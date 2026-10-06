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
from radar.backtest.runner import (_engine_config, _rules, load_backtest_config,
                                   load_spy_ma200_guard, split_dates)
from radar.lab.data import (MARKET_FEATURE_VERSION, available_features,
                            load_strategy_segment, source_watermark)
from radar.lab.execution import resolve_exit_policy
from radar.lab.parameters import engine_legacy_fields, research_hash
from radar.lab.store import RunStore
from radar.lab.universe import load_universe
from radar.lab.terminal import load_terminal_events
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
                          (root / ("src/radar/lean/algorithm.py" if metadata.get('engine') == 'lean' else
                                   "src/radar/backtest/engine.py"), "engine_code_hash"),
                          (root / "src" / "radar" / "strategy" / "adapter.py", "adapter_code_hash"),
                          (root / "src" / "radar" / "strategy" / "full_strategy2.py",
                           "legacy_strategy_code_hash")):
            if sha256_file(path) != metadata[key]:
                raise ValueError(f"run source changed after queuing: {path.name}")
        for relative, expected in metadata.get("host_source_hashes", {}).items():
            if sha256_file(root / relative) != expected:
                raise ValueError(f"run host source changed after queuing: {relative}")
        if (metadata["feature_version"] != FEATURE_VERSION or
                metadata.get("market_feature_version") != MARKET_FEATURE_VERSION):
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
        resolved = metadata.get("resolved_config")
        if resolved is not None:
            values = resolved["values"]
            if research_hash(values) != resolved["hash"] or (
                    metadata.get("resolved_config_hash") != resolved["hash"]):
                raise ValueError("queued resolved configuration hash changed")
            if values["dataset"]["data_snapshot"] != metadata["data_snapshot"]:
                raise ValueError("queued dataset snapshot differs from run metadata")
            if values["dataset"].get("market_feature_version") != metadata["market_feature_version"]:
                raise ValueError("queued market feature version differs from run metadata")
            policy = engine_legacy_fields(values["execution"])
            if policy != metadata["execution_policy"]:
                raise ValueError("queued execution policy differs from resolved configuration")
            raw = {**raw, **policy}
        else:
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
        covered_sessions = [day for day in split["sessions"]
                            if dates[0] <= day <= dates[2]]
        universe_provider, provenance = load_universe(
            root, metadata.get("universe_mode", "current_snapshot"), covered_sessions)
        terminal = load_terminal_events(root) if universe_provider is not None else None
        if (terminal.fingerprint if terminal else None) != (
                metadata.get("resolved_config") or {}).get("values", {}).get(
                    "dataset", {}).get("terminal_fingerprint"):
            raise ValueError("queued terminal event source changed")
        if terminal is not None:
            terminal.validate_coverage(covered_sessions)
        if metadata.get("resolved_config") and (
                provenance.fingerprint != values["dataset"]["universe_fingerprint"]):
            raise ValueError("queued PIT security master changed")
        load_args = (database, dates[0], dates[2], set(manifest.required_features))
        frame = load_strategy_segment(*load_args, universe_provider) if universe_provider else (
            load_strategy_segment(*load_args))
        config = _engine_config(
            raw, variant="full_strategy2", allocator=raw.get("allocator", "equal_cash"),
            slippage_bps=float(raw.get("slippage_bps", metadata["slippage_bps"])),
            max_position_fraction=float(raw["max_position_fraction"]),
            market_guard=raw.get("market_guard", "none"),
        )
        if isinstance(config, BacktestConfig):
            config = replace(config, execution_timing=metadata["execution_policy"].get(
                "execution_timing", "legacy_close"),
                fail_on_missing_marks=universe_provider is not None)
        source_scanner = metadata.get("source_scanner_run_id")
        if source_scanner:
            study = store.get_scanner_run(source_scanner)
            if study["status"] != "completed" or not store.verify_scanner_artifacts(source_scanner):
                raise ValueError("source Scanner artifact is unavailable or changed")
            source_meta = study["metadata"]
            if (source_meta.get("strategy_code_hash") != metadata.get("strategy_code_hash") or
                    source_meta.get("adapter_code_hash") != metadata.get("adapter_code_hash") or
                    source_meta != metadata.get("signal_source_provenance")):
                raise ValueError("source Scanner signal-producing implementation provenance differs")
            if (source_meta.get("strategy_id") != metadata["strategy_id"] or
                    source_meta.get("strategy_version") != metadata["strategy_version"] or
                    source_meta.get("config_hash") != metadata["config_hash"] or
                    source_meta.get("data_snapshot") != metadata["data_snapshot"] or
                    source_meta.get("universe_mode", "current_snapshot") != metadata.get("universe_mode", "current_snapshot") or
                    source_meta.get("signal_start") != metadata["window"][0] or
                    source_meta.get("signal_end") != metadata["window"][1]):
                raise ValueError("source Scanner provenance differs from Backtest")
            selected = store.get_scanner_candidates(source_scanner, limit=10_000_000)
            by_day: dict[str, list[dict]] = {}
            for row in selected:
                if row["selected"]:
                    by_day.setdefault(row["signal_date"], []).append(row)

            def selector(daily: pd.DataFrame, already_held: set[str]) -> pd.DataFrame:
                day = str(pd.Timestamp(daily["date"].iloc[0]).date())
                rows = by_day.get(day, [])
                symbols = [row["symbol"] for row in rows if row["symbol"] not in already_held]
                chosen = daily.set_index("symbol", drop=False).reindex(symbols).dropna(subset=["symbol"])
                if chosen.empty:
                    return daily.iloc[0:0].copy()
                scores = {row["symbol"]: row["strategy_score"] for row in rows}
                chosen = chosen.copy()
                chosen["strategy2_score"] = chosen["symbol"].map(scores)
                return chosen.head(int(raw["max_new_candidates"])).reset_index(drop=True)
        else:
            selector = make_candidate_selector(
                registration.plugin, metadata["config"],
                max_new=int(raw["max_new_candidates"]),
            )
        pace_ms = int(metadata.get("pace_ms", 0))
        if not 0 <= pace_ms <= 2000:
            raise ValueError("invalid timeline pace")
        if metadata.get('engine') == 'lean':
            from radar.lean.integration import execute
            return execute(root, store, run_id, metadata, frame, split['sessions'], registration, fees)

        def report_progress(snapshot: dict) -> None:
            store.append_progress(run_id, snapshot)
            if pace_ms:
                time.sleep(pace_ms / 1000)

        result = run_backtest(
            frame, split["sessions"], signal_start=dates[0],
            signal_end=dates[1], evaluation_end=dates[2],
            rules=_rules(raw), fee_config=fees, config=config,
            candidate_selector=selector,
            market_ok=(load_spy_ma200_guard(database, dates[2])
                       if raw.get("market_guard", "none") == "spy_ma200" else None),
            progress_callback=report_progress,
            cancel_requested=lambda: store.get_run(run_id)["cancel_requested"],
            terminal_provider=terminal,
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
        if store.get_run(run_id)['cancel_requested']:
            store.cancel_run(run_id)
            return {'status': 'cancelled'}
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

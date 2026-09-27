"""Isolated, read-only market-data scanner worker."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import traceback

import numpy as np
import pandas as pd

from radar.backtest.runner import split_dates
from radar.lab.data import (MARKET_FEATURES, MARKET_FEATURE_VERSION, available_features,
                            load_forward_bars, load_strategy_segment, source_watermark)
from radar.lab.scanner import LABEL_VERSION, build_labels, candidate_metrics
from radar.lab.store import RunStore
from radar.lab.worker import sha256_file
from radar.research.pipeline import FEATURE_VERSION
from radar.strategy.adapter import evaluate_selection
from radar.strategy.loader import load_strategy_directory


def scan_frames(plugin, config: dict, feature_frame: pd.DataFrame, bars: pd.DataFrame,
                sessions: pd.DatetimeIndex, signal_start: pd.Timestamp,
                signal_end: pd.Timestamp, evaluation: dict,
                progress=None) -> tuple[list[dict], dict]:
    """One causal selection pass; forward OHLC is used only after it returns."""
    required = set(plugin.required_features())
    candidate_parts: list[pd.DataFrame] = []
    background_parts: list[pd.DataFrame] = []
    diagnostic_columns: set[str] = set()
    signal_days = sessions[(sessions >= signal_start) & (sessions <= signal_end)]
    for ordinal, day in enumerate(signal_days, 1):
        try:
            daily = feature_frame.xs(day, level="date", drop_level=False).copy()
        except KeyError:
            continue
        eligible = daily[daily["tradability_pass"].fillna(False).astype(bool)].copy()
        for name in required:
            if name in eligible.columns and pd.api.types.is_numeric_dtype(eligible[name]):
                eligible = eligible[np.isfinite(pd.to_numeric(eligible[name], errors="coerce"))]
        ranked, _ = evaluate_selection(plugin, config, eligible, diagnostics=True)
        if not ranked.empty:
            diagnostic_columns.update(ranked.attrs.get("diagnostic_columns", []))
            ranked["signal_date"] = pd.Timestamp(day)
            for name in MARKET_FEATURES & set(daily.columns):
                ranked[name] = daily.set_index("symbol").loc[ranked["symbol"], name].to_numpy()
            candidate_parts.append(ranked)
        background_parts.append(pd.DataFrame({"signal_date": day, "symbol": eligible["symbol"]}))
        if progress:
            progress({"date": str(day.date()), "completed_sessions": ordinal,
                      "total_sessions": len(signal_days),
                      "candidate_count": sum(len(item) for item in candidate_parts)})
    candidates = pd.concat(candidate_parts, ignore_index=True) if candidate_parts else pd.DataFrame(
        columns=["signal_date", "symbol", "security_name", "rank", "strategy_score", "selected"])
    background = pd.concat(background_parts, ignore_index=True) if background_parts else pd.DataFrame(
        columns=["signal_date", "symbol"])
    if not background.empty:
        background["label"] = build_labels(background, bars, sessions, evaluation)["label"]
    else:
        background["label"] = []
    if not candidates.empty:
        label_lookup = {(row.signal_date, row.symbol): row.label for row in background.itertuples()}
        candidates["label"] = [label_lookup.get((row.signal_date, row.symbol))
                               for row in candidates.itertuples()]
        # A strategy may select a symbol outside the base universe; label it,
        # but keep the base-rate denominator strictly tradable and feature-complete.
        outside = candidates["label"].isna()
        if outside.any():
            candidates.loc[outside, "label"] = build_labels(
                candidates.loc[outside, ["signal_date", "symbol"]], bars, sessions, evaluation,
            )["label"].to_list()
    else:
        candidates["label"] = []
    metrics = candidate_metrics(candidates, background, evaluation)
    rows = []
    context_names = sorted(MARKET_FEATURES & set(candidates.columns))
    for row in candidates.to_dict("records"):
        diagnostics = {name: float(row[name]) for name in diagnostic_columns
                       if not name.startswith("p_") and name in row and pd.notna(row[name])}
        probabilities = {name: float(row[name]) for name in diagnostic_columns
                         if name.startswith("p_") and name in row and pd.notna(row[name])}
        rows.append({"signal_date": row["signal_date"], "symbol": row["symbol"],
                     "security_name": row["security_name"], "rank": int(row["rank"]),
                     "strategy_score": float(row["strategy_score"]),
                     "selected": bool(row["selected"]), "diagnostics": diagnostics,
                     "probabilities": probabilities, "label": row["label"],
                     "features": {name: row.get(name) for name in sorted(required | {"close"})},
                     "market_context": {name: float(row[name]) for name in context_names
                                        if pd.notna(row[name])}})
    if rows:
        regime = pd.DataFrame(rows)
        for label, condition in (("spy_above_ma20", lambda x: x >= 0),
                                 ("spy_below_ma20", lambda x: x < 0)):
            subset = regime[regime["market_context"].map(
                lambda x: "spy_trend" in x and condition(x["spy_trend"]))]
            metrics[f"{label}_candidate_count"] = int(len(subset))
            hit = metrics["primary_target"]
            labeled = [item[hit] for item in subset["label"] if item is not None]
            metrics[f"{label}_hit_rate"] = float(np.mean(labeled)) if labeled else None
    return rows, metrics


def execute_scanner_run(root: Path, store_path: Path, run_id: str) -> dict:
    root = root.resolve()
    store = RunStore(store_path)
    metadata = store.get_scanner_run(run_id)["metadata"]
    store.start_scanner_run(run_id, os.getpid())
    try:
        database = root / "data" / "phase2-research.duckdb"
        strategy_path = Path(metadata["strategy_path"])
        for path, key in ((database, "data_snapshot"),
                          (strategy_path / "strategy.py", "strategy_code_hash"),
                          (strategy_path / "manifest.yaml", "strategy_manifest_hash"),
                          (root / "src" / "radar" / "strategy" / "adapter.py", "adapter_code_hash"),
                          (root / "src" / "radar" / "lab" / "scanner.py", "scanner_code_hash"),
                          (root / "src" / "radar" / "lab" / "scanner_worker.py", "scanner_worker_code_hash"),
                          (root / "src" / "radar" / "lab" / "data.py", "data_code_hash"),
                          (root / "config" / "research.yaml", "research_config_hash")):
            if sha256_file(path) != metadata[key]:
                raise ValueError(f"scanner source changed after queuing: {path.name}")
        for relative, expected in metadata["host_source_hashes"].items():
            if sha256_file(root / relative) != expected:
                raise ValueError(f"scanner host source changed after queuing: {relative}")
        if (metadata["feature_version"] != FEATURE_VERSION or
                metadata["market_feature_version"] != MARKET_FEATURE_VERSION or
                metadata["label_version"] != LABEL_VERSION or
                source_watermark(database) != metadata["source_watermark"]):
            raise ValueError("scanner data or label version changed after queuing")
        registration = load_strategy_directory(
            strategy_path, available_features(database), run_tests=True)
        manifest = registration.manifest
        if (manifest.id, manifest.version, manifest.interface_version) != (
                metadata["strategy_id"], metadata["strategy_version"],
                metadata["plugin_interface_version"]):
            raise ValueError("strategy identity changed after queuing")
        split = split_dates(database, root / "config" / "research.yaml")
        sessions = pd.DatetimeIndex(split["sessions"])
        start, end = pd.Timestamp(metadata["signal_start"]), pd.Timestamp(metadata["signal_end"])
        frame = load_strategy_segment(database, start, end,
                                      set(manifest.required_features) | MARKET_FEATURES)
        last = sessions.searchsorted(end, side="right") + metadata["evaluation"]["horizon_sessions"]
        bar_end = sessions[min(last, len(sessions)) - 1]
        bars = load_forward_bars(database, start, bar_end)
        rows, metrics = scan_frames(registration.plugin, metadata["config"], frame, bars,
                                    sessions, start, end, metadata["evaluation"],
                                    progress=lambda value: store.scanner_progress(run_id, value))
        store.finish_scanner_run(run_id, rows, metrics)
        return metrics
    except Exception as error:
        store.fail_scanner_run(run_id, f"{type(error).__name__}: {error}")
        raise


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--store", type=Path, required=True)
    parser.add_argument("--run", required=True)
    args = parser.parse_args()
    try:
        execute_scanner_run(args.root, args.store, args.run)
    except Exception:
        traceback.print_exc()
        raise SystemExit(1)


if __name__ == "__main__":
    main()

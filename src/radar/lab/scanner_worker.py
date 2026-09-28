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
from radar.lab.parameters import research_hash
from radar.lab.scanner import (LABEL_VERSION, build_labels, candidate_metrics,
                               signal_event_flags)
from radar.lab.store import RunStore
from radar.lab.universe import load_universe
from radar.lab.worker import sha256_file
from radar.research.pipeline import FEATURE_VERSION
from radar.strategy.adapter import evaluate_filter_diagnostics, evaluate_selection
from radar.strategy.loader import load_strategy_directory


def scan_frames(plugin, config: dict, feature_frame: pd.DataFrame, bars: pd.DataFrame,
                sessions: pd.DatetimeIndex, signal_start: pd.Timestamp,
                signal_end: pd.Timestamp, evaluation: dict,
                progress=None, universe_provider=None) -> tuple[list[dict], dict]:
    """One causal selection pass; forward OHLC is used only after it returns."""
    required = set(plugin.required_features())
    candidate_parts: list[pd.DataFrame] = []
    background_parts: list[pd.DataFrame] = []
    diagnostic_columns: set[str] = set()
    funnel_by_day: list[dict] = []
    near_misses: list[dict] = []
    signal_days = sessions[(sessions >= signal_start) & (sessions <= signal_end)]
    for ordinal, day in enumerate(signal_days, 1):
        try:
            daily = feature_frame.xs(day, level="date", drop_level=False).copy()
        except KeyError:
            continue
        funnel = {"date": str(pd.Timestamp(day).date()),
                  "eligible_universe": int(len(daily))}
        tradable = daily["tradability_pass"].fillna(False).astype(bool)
        funnel["tradable"] = int(tradable.sum())
        eligible = daily[daily["tradability_pass"].fillna(False).astype(bool)].copy()
        for name in required:
            if name in eligible.columns and pd.api.types.is_numeric_dtype(eligible[name]):
                eligible = eligible[np.isfinite(pd.to_numeric(eligible[name], errors="coerce"))]
        funnel["feature_complete"] = int(len(eligible))
        if not eligible.empty:
            stages = evaluate_filter_diagnostics(plugin, config, eligible)
            surviving = pd.Series(True, index=stages.index)
            for name in stages:
                surviving &= stages[name]
                funnel[name.removeprefix("filter_pass_")] = int(surviving.sum())
            if len(near_misses) < 500 and len(stages.columns):
                misses = stages.loc[~surviving].copy()
                misses["_failed_count"] = (~misses).sum(axis=1)
                misses = misses.sort_values("_failed_count", kind="stable")
                for index, result in misses.head(min(20, 500 - len(near_misses))).iterrows():
                    near_misses.append({
                        "date": funnel["date"],
                        "symbol": str(eligible.iloc[index]["symbol"]),
                        "stages": {name.removeprefix("filter_pass_"): bool(result[name])
                                   for name in stages.columns},
                    })
        ranked, _ = evaluate_selection(plugin, config, eligible, diagnostics=True)
        funnel["final_ranked_candidate"] = int(len(ranked))
        funnel_by_day.append(funnel)
        if not ranked.empty:
            diagnostic_columns.update(ranked.attrs.get("diagnostic_columns", []))
            ranked["signal_date"] = pd.Timestamp(day)
            if "security_id" in daily:
                ranked["security_id"] = daily.set_index("symbol").loc[
                    ranked["symbol"], "security_id"].to_numpy()
            for name in MARKET_FEATURES & set(daily.columns):
                ranked[name] = daily.set_index("symbol").loc[ranked["symbol"], name].to_numpy()
            candidate_parts.append(ranked)
        base = {"signal_date": day, "symbol": eligible["symbol"]}
        if universe_provider is not None:
            base["security_id"] = eligible["security_id"]
        background_parts.append(pd.DataFrame(base))
        if progress:
            progress({"date": str(day.date()), "completed_sessions": ordinal,
                      "total_sessions": len(signal_days),
                      "candidate_count": sum(len(item) for item in candidate_parts)})
    candidates = pd.concat(candidate_parts, ignore_index=True) if candidate_parts else pd.DataFrame(
        columns=["signal_date", "symbol", "security_name", "rank", "strategy_score", "selected"])
    background = pd.concat(background_parts, ignore_index=True) if background_parts else pd.DataFrame(
        columns=["signal_date", "symbol"])
    label_bars = bars
    label_background = background
    known_ends: dict[str, pd.Timestamp] = {}
    if universe_provider is not None and not background.empty:
        # Forward outcomes follow stable identity across dated ticker mappings.
        # This also prevents a reused ticker from inheriting another entity's bars.
        label_bars = universe_provider.filter_frame(bars).reset_index(drop=True)
        label_bars["symbol"] = label_bars["security_id"]
        label_background = background.copy()
        label_background["symbol"] = label_background["security_id"]
        for security_id, mappings in universe_provider.frame.groupby("security_id"):
            eligible = mappings[mappings["eligible"]]
            if eligible.empty:
                continue
            ends = [row.delisting_date if pd.notna(row.delisting_date) else row.valid_to
                    for row in eligible.itertuples(index=False)]
            if all(pd.notna(end) for end in ends):
                known_ends[str(security_id)] = max(pd.Timestamp(end) for end in ends)
    if not background.empty:
        labels = build_labels(label_background, label_bars, sessions, evaluation,
                              known_ends, primary_only=True)
        for field in ("label", "label_status", "label_reason"):
            background[field] = labels[field]
    else:
        background["label"] = []
        background["label_status"] = []
        background["label_reason"] = []
    if not candidates.empty:
        label_candidates = candidates[["signal_date", "symbol"]].copy()
        if universe_provider is not None:
            label_candidates["symbol"] = candidates["security_id"]
        labels = build_labels(label_candidates, label_bars, sessions, evaluation, known_ends)
        for field in ("label", "label_status", "label_reason"):
            candidates[field] = labels[field]
    else:
        candidates["label"] = []
        candidates["label_status"] = []
        candidates["label_reason"] = []
    metrics = candidate_metrics(candidates, background, evaluation, sessions)
    metrics["funnel_by_day"] = funnel_by_day
    metrics["near_misses"] = near_misses
    rows = []
    event_flags = signal_event_flags(
        candidates, evaluation["event_cooldown_sessions"], sessions)
    context_names = sorted(MARKET_FEATURES & set(candidates.columns))
    for index, row in enumerate(candidates.to_dict("records")):
        diagnostics = {name: float(row[name]) for name in diagnostic_columns
                       if not name.startswith("p_") and name in row and pd.notna(row[name])}
        probabilities = {name: float(row[name]) for name in diagnostic_columns
                         if name.startswith("p_") and name in row and pd.notna(row[name])}
        rows.append({"signal_date": row["signal_date"], "symbol": row["symbol"],
                     "security_name": row["security_name"], "rank": int(row["rank"]),
                     "strategy_score": float(row["strategy_score"]),
                     "selected": bool(row["selected"]), "diagnostics": diagnostics,
                     "probabilities": probabilities, "label": row["label"],
                     "label_status": row["label_status"], "label_reason": row["label_reason"],
                     "security_id": row.get("security_id"),
                     "signal_event": event_flags[index],
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
            outcome = metrics["primary_outcome"]
            labeled = [item[outcome] for item in subset["label"]
                       if item is not None and item.get(outcome) is not None]
            metrics[f"{label}_labeled_count"] = len(labeled)
            metrics[f"{label}_success_rate"] = float(np.mean(labeled)) if labeled else None
    return rows, metrics


def execute_scanner_run(root: Path, store_path: Path, run_id: str) -> dict:
    root = root.resolve()
    store = RunStore(store_path)
    metadata = store.get_scanner_run(run_id)["metadata"]
    store.start_scanner_run(run_id, os.getpid())
    try:
        resolved = metadata.get("resolved_config")
        if resolved is not None and (
                research_hash(resolved["values"]) != resolved["hash"] or
                resolved["hash"] != metadata["resolved_config_hash"]):
            raise ValueError("queued Scanner resolved configuration hash changed")
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
        coverage_end = (pd.Timestamp(metadata["resolved_config"]["values"]["dataset"]["evaluation_end"])
                        if metadata.get("resolved_config") else end)
        covered_sessions = sessions[(sessions >= start) & (sessions <= coverage_end)]
        provider, provenance = load_universe(
            root, metadata.get("universe_mode", "current_snapshot"), covered_sessions)
        if metadata.get("resolved_config") and (
                provenance.fingerprint != metadata["resolved_config"]["values"]["dataset"][
                    "universe_fingerprint"]):
            raise ValueError("queued PIT security master changed")
        load_args = (database, start, end, set(manifest.required_features) | MARKET_FEATURES)
        frame = load_strategy_segment(*load_args, provider) if provider else (
            load_strategy_segment(*load_args))
        last = sessions.searchsorted(end, side="right") + metadata["evaluation"]["horizon_sessions"]
        bar_end = sessions[min(last, len(sessions)) - 1]
        bars = load_forward_bars(database, start, bar_end)
        rows, metrics = scan_frames(registration.plugin, metadata["config"], frame, bars,
                                    sessions, start, end, metadata["evaluation"],
                                    progress=lambda value: store.scanner_progress(run_id, value),
                                    universe_provider=provider)
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

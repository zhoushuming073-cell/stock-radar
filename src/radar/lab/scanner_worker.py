"""Isolated, read-only market-data scanner worker."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import traceback
from typing import Mapping

import duckdb
import numpy as np
import pandas as pd
import yaml

from radar.backtest.runner import split_dates
from radar.lab.data import (MARKET_FEATURES, MARKET_FEATURE_VERSION, available_features,
                            load_forward_bars, load_strategy_segment, source_watermark)
from radar.lab.parameters import research_hash
from radar.lab.scanner import (LABEL_VERSION, build_labels, candidate_metrics,
                               signal_event_flags, validate_frozen_horizon)
from radar.lab.store import RunStore
from radar.lab.universe import load_universe, validate_frozen_feature_store
from radar.lab.terminal import load_terminal_events, TERMINAL_LABEL_VERSION
from radar.lab.worker import sha256_file
from radar.research.pipeline import FEATURE_VERSION
from radar.strategy.adapter import evaluate_filter_diagnostics, evaluate_selection
from radar.strategy.loader import load_strategy_directory


class ScannerCancelled(Exception):
    """A running scan reached a safe session boundary after cancellation."""


def signal_session_coverage(feature_frame: pd.DataFrame, sessions: pd.DatetimeIndex,
                            signal_start: pd.Timestamp, signal_end: pd.Timestamp,
                            expected_counts: Mapping[str, int] | None = None) -> dict:
    expected = pd.DatetimeIndex(sessions[(sessions >= signal_start) & (sessions <= signal_end)]).normalize()
    observed = pd.DatetimeIndex(feature_frame.index.get_level_values("date").unique()).normalize()
    missing = expected.difference(observed)
    counts = feature_frame.groupby(level="date").size()
    incomplete = []
    for index, date in enumerate(expected):
        key = str(date.date())
        count = int(counts.get(date, 0))
        if not count:
            continue
        published = expected_counts.get(key) if expected_counts is not None else None
        if published is not None:
            baseline, minimum_ratio, source = int(published), .5, "published_manifest"
        else:
            neighbors = [int(counts.get(other, 0)) for other in
                         expected[max(0, index - 5):index].append(expected[index + 1:index + 6])]
            neighbors = [value for value in neighbors if value > 0]
            baseline = float(np.median(neighbors)) if len(neighbors) >= 2 else 0
            minimum_ratio, source = .25, "nearby_median"
        if baseline and count < baseline * minimum_ratio:
            incomplete.append({"date": key, "observed": count,
                               "expected": baseline, "source": source})
    return {"expected_signal_sessions": len(expected),
            "observed_signal_sessions": len(expected) - len(missing),
            "missing_signal_sessions": [str(day.date()) for day in missing],
            "incomplete_signal_sessions": incomplete}


def published_session_counts(database: Path, start: pd.Timestamp,
                             end: pd.Timestamp) -> dict[str, int] | None:
    with duckdb.connect(str(database), read_only=True) as connection:
        available = connection.execute("""
            SELECT COUNT(*) FROM information_schema.tables
            WHERE table_name='feature_session_coverage'
        """).fetchone()[0]
        if not available:
            return None
        rows = connection.execute("""
            SELECT date,row_count FROM feature_session_coverage
            WHERE feature_version=? AND date BETWEEN ? AND ?
        """, [FEATURE_VERSION, start.date(), end.date()]).fetchall()
    return {str(day): int(count) for day, count in rows}


def scan_frames(plugin, config: dict, feature_frame: pd.DataFrame, bars: pd.DataFrame,
                sessions: pd.DatetimeIndex, signal_start: pd.Timestamp,
                signal_end: pd.Timestamp, evaluation: dict,
                progress=None, universe_provider=None, terminal_provider=None,
                expected_counts: Mapping[str, int] | None = None) -> tuple[list[dict], dict]:
    """One causal selection pass; forward OHLC is used only after it returns."""
    if universe_provider is not None:
        feature_frame = universe_provider.filter_frame(feature_frame)
    required = set(plugin.required_features())
    candidate_parts: list[pd.DataFrame] = []
    background_parts: list[pd.DataFrame] = []
    diagnostic_columns: set[str] = set()
    funnel_by_day: list[dict] = []
    near_misses: list[dict] = []
    signal_days = sessions[(sessions >= signal_start) & (sessions <= signal_end)]
    coverage = signal_session_coverage(feature_frame, sessions, signal_start, signal_end,
                                       expected_counts)
    if coverage["missing_signal_sessions"]:
        raise ValueError("Scanner feature coverage missing full signal sessions: " +
                         ", ".join(coverage["missing_signal_sessions"][:20]))
    if coverage["incomplete_signal_sessions"]:
        raise ValueError("Scanner feature coverage incomplete signal sessions: " +
                         str(coverage["incomplete_signal_sessions"][:20]))
    for ordinal, day in enumerate(signal_days, 1):
        daily = feature_frame.xs(day, level="date", drop_level=False).copy()
        funnel = {"date": str(pd.Timestamp(day).date()),
                  "eligible_universe": int(len(daily))}
        if universe_provider is not None:
            membership_count = len(universe_provider.eligible_on(day))
            funnel["pit_membership"] = membership_count
            funnel["missing_feature_or_price"] = membership_count - len(daily)
            price_day = pd.to_datetime(bars["date"]).dt.normalize().eq(day)
            observed_prices = universe_provider.filter_frame(bars.loc[price_day]).reset_index(drop=True)
            priced = set(observed_prices.security_id)
            members = set(universe_provider.eligible_on(day).security_id)
            with_features = set(daily.security_id)
            history = daily.get("pit_history_sessions", pd.Series(np.nan, index=daily.index))
            insufficient = history.lt(126)
            funnel["no_price"] = len(members - priced)
            funnel["insufficient_warmup"] = int(insufficient.sum())
            funnel["warmup_unknown"] = int(history.isna().sum())
            feature_missing = len((members & priced) - with_features)
        tradable = daily["tradability_pass"].fillna(False).astype(bool)
        funnel["tradable"] = int(tradable.sum())
        eligible = daily[daily["tradability_pass"].fillna(False).astype(bool)].copy()
        for name in required:
            if name in eligible.columns and pd.api.types.is_numeric_dtype(eligible[name]):
                eligible = eligible[np.isfinite(pd.to_numeric(eligible[name], errors="coerce"))]
        funnel["feature_complete"] = int(len(eligible))
        if universe_provider is not None:
            funnel["feature_unavailable"] = feature_missing + int((tradable & ~insufficient).sum()) - len(eligible)
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
        if universe_provider is not None:
            funnel["strategy_rejected"] = (membership_count - funnel["no_price"] - funnel["insufficient_warmup"]
                                            - funnel["feature_unavailable"] - len(ranked))
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
                              known_ends, primary_only=True,
                              terminal_provider=terminal_provider)
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
        labels = build_labels(label_candidates, label_bars, sessions, evaluation, known_ends,
                              terminal_provider=terminal_provider)
        for field in ("label", "label_status", "label_reason"):
            candidates[field] = labels[field]
    else:
        candidates["label"] = []
        candidates["label_status"] = []
        candidates["label_reason"] = []
    metrics = candidate_metrics(candidates, background, evaluation, sessions)
    if terminal_provider is not None:
        metrics["label_version"] = TERMINAL_LABEL_VERSION
    metrics["funnel_by_day"] = funnel_by_day
    metrics["near_misses"] = near_misses
    metrics["coverage"] = coverage
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
    def report_progress(value: dict) -> None:
        if store.get_scanner_run(run_id)["status"] == "cancel_requested":
            raise ScannerCancelled()
        store.scanner_progress(run_id, value)
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
                metadata["label_version"] not in {LABEL_VERSION, TERMINAL_LABEL_VERSION} or
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
        validate_frozen_horizon(metadata["evaluation"], yaml.safe_load(
            (root / "config/research.yaml").read_text(encoding="utf-8")))
        start, end = pd.Timestamp(metadata["signal_start"]), pd.Timestamp(metadata["signal_end"])
        coverage_end = (pd.Timestamp(metadata["resolved_config"]["values"]["dataset"]["evaluation_end"])
                        if metadata.get("resolved_config") else pd.Timestamp(split[metadata["split"]][2]))
        # Forward outcome sessions and OHLC are physically bounded, including
        # when the last signal has less than a complete label horizon left.
        sessions = sessions[sessions <= coverage_end]
        covered_sessions = sessions[(sessions >= start) & (sessions <= coverage_end)]
        provider, provenance = load_universe(
            root, metadata.get("universe_mode", "current_snapshot"), covered_sessions)
        terminal = (load_terminal_events(root) if provider is not None and
                    metadata["label_version"] == TERMINAL_LABEL_VERSION else None)
        if (terminal.fingerprint if terminal else None) != (
                metadata.get("resolved_config") or {}).get("values", {}).get(
                    "dataset", {}).get("terminal_fingerprint"):
            raise ValueError("queued terminal event source changed")
        if terminal is not None:
            terminal.validate_coverage(covered_sessions)
        if metadata.get("resolved_config") and (
                provenance.fingerprint != metadata["resolved_config"]["values"]["dataset"][
                    "universe_fingerprint"]):
            raise ValueError("queued PIT security master changed")
        validate_frozen_feature_store(provenance, metadata)
        load_args = (database, start, end, set(manifest.required_features) | MARKET_FEATURES)
        frame = load_strategy_segment(*load_args, provider) if provider else (
            load_strategy_segment(*load_args))
        expected_counts = (published_session_counts(database, start, end)
                           if provider is None else None)
        coverage = signal_session_coverage(frame, sessions, start, end, expected_counts)
        report_progress({"coverage": coverage})
        if coverage["missing_signal_sessions"]:
            raise ValueError("Scanner feature coverage missing full signal sessions: " +
                             ", ".join(coverage["missing_signal_sessions"][:20]))
        if coverage["incomplete_signal_sessions"]:
            raise ValueError("Scanner feature coverage incomplete signal sessions: " +
                             str(coverage["incomplete_signal_sessions"][:20]))
        last = sessions.searchsorted(end, side="right") + metadata["evaluation"]["horizon_sessions"]
        bar_end = min(coverage_end, sessions[min(last, len(sessions)) - 1])
        bars = (load_forward_bars(database, start, bar_end, provider) if provider else
                load_forward_bars(database, start, bar_end))
        rows, metrics = scan_frames(registration.plugin, metadata["config"], frame, bars,
                                    sessions, start, end, metadata["evaluation"],
                                    progress=report_progress,
                                    universe_provider=provider, terminal_provider=terminal,
                                    expected_counts=expected_counts)
        if store.get_scanner_run(run_id)["status"] == "cancel_requested":
            raise ScannerCancelled()
        store.finish_scanner_run(run_id, rows, metrics)
        return metrics
    except ScannerCancelled:
        store.finish_scanner_cancel(run_id)
        return {"cancelled": True}
    except Exception as error:
        if store.get_scanner_run(run_id)["status"] == "cancel_requested":
            store.finish_scanner_cancel(run_id)
            return {"cancelled": True}
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

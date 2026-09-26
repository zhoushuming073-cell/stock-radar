"""Research runner for the full Strategy 2 lifecycle candidate.

The old final Test was already viewed under another rule. Results here are
historical exploratory comparisons, not a new untouched out-of-sample test.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from radar.backtest.costs import load_fee_config
from radar.backtest.engine import run_backtest
from radar.backtest.metrics import summarize_backtest
from radar.backtest.runner import _engine_config, _rules, load_backtest_config, split_dates
from radar.research.pipeline import FEATURE_VERSION
from radar.strategy.full_strategy2 import FullStrategy2Rules, rank_full_strategy2


FULL_FEATURE_COLUMNS = (
    "ret_60", "drawdown_60", "drawdown_20", "pullback_days_20",
    "decline_speed_prev_3", "decline_acceleration", "red_body_avg_3",
    "red_body_avg_5", "range_contraction", "volume_contraction",
    "lower_wick_ratio", "close_location", "failed_breakdown",
    "support_reclaim", "new_low_frequency_5", "higher_low_proxy",
    "ret_1", "body_pct", "reclaim_ma_5", "rebound_from_low_5",
    "dist_ma_5", "elasticity_score", "tradability_pass",
    "avg_dollar_volume_20",
)


def load_full_segment(database: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Load only bars and causal feature columns for a single split."""
    selected = ", ".join(f"f.{column}" for column in FULL_FEATURE_COLUMNS)
    connection = duckdb.connect(str(database), read_only=True)
    try:
        frame = connection.execute(f"""
            SELECT f.date, f.symbol, b.open, b.close, {selected},
                   a.name AS security_name
            FROM daily_features f
            JOIN daily_bars b ON f.date=b.date AND f.symbol=b.symbol
            JOIN assets a ON f.symbol=a.symbol
            WHERE f.feature_version=? AND f.date BETWEEN ? AND ?
        """, [FEATURE_VERSION, start.date(), end.date()]).df()
    finally:
        connection.close()
    if frame.empty:
        raise ValueError(f"no features from {start.date()} through {end.date()}")
    frame["date"] = pd.to_datetime(frame["date"])
    if frame.duplicated(["date", "symbol"]).any():
        raise ValueError("duplicate symbol/session in research features")
    return frame.set_index(["date", "symbol"], drop=False).sort_index()


def _full_rules(path: Path) -> tuple[FullStrategy2Rules, dict]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("version") != "full_strategy2_v1_exploratory":
        raise ValueError("wrong full Strategy 2 configuration version")
    defaults = FullStrategy2Rules.__dataclass_fields__
    keys = set(defaults)
    if not keys.issubset(raw):
        raise ValueError(f"missing full Strategy 2 rules: {sorted(keys - set(raw))}")
    return FullStrategy2Rules(**{key: raw[key] for key in keys}), raw


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_full_strategy2(
    database: Path, research_config: Path, backtest_config: Path,
    full_config: Path, output_dir: Path, *, splits: tuple[str, ...],
) -> dict:
    """Run explicitly requested splits and slippage scenarios, with ledgers at 10 bps."""
    if not splits or any(name not in {"train", "validation", "test"} for name in splits):
        raise ValueError("splits must name train, validation, or test")
    full_rules, full_raw = _full_rules(full_config)
    backtest_raw = load_backtest_config(backtest_config)
    fees = load_fee_config(research_config)
    split = split_dates(database, research_config)
    scenarios = [float(value) for value in full_raw["slippage_sensitivity_bps"]]
    if len(set(scenarios)) != len(scenarios) or any(value < 0 for value in scenarios):
        raise ValueError("invalid slippage scenarios")
    output_dir.mkdir(parents=True, exist_ok=True)
    previous_manifest_path = output_dir / "manifest.json"
    old_manifest = (json.loads(previous_manifest_path.read_text(encoding="utf-8"))
                    if previous_manifest_path.exists() else {})
    expected_hashes = {
        "full_config_sha256": _sha256(full_config),
        "backtest_config_sha256": _sha256(backtest_config),
        "research_config_sha256": _sha256(research_config),
        "strategy_code_sha256": _sha256(Path(__file__).parents[1] / "strategy" / "full_strategy2.py"),
        "engine_code_sha256": _sha256(Path(__file__).with_name("engine.py")),
    }
    for key, expected in expected_hashes.items():
        if key in old_manifest and old_manifest[key] != expected:
            raise ValueError(f"existing full Strategy 2 results use another {key}")
    rows: list[dict] = []
    for name in splits:
        dates = split[name]
        frame = load_full_segment(database, dates[0], dates[2])
        selector = lambda daily, held: rank_full_strategy2(
            daily, full_rules, already_held=held)
        for bps in scenarios:
            config = _engine_config(backtest_raw, variant="full_strategy2",
                                    allocator=full_raw["allocator"],
                                    slippage_bps=bps,
                                    max_position_fraction=float(backtest_raw["max_position_fraction"]))
            result = run_backtest(
                frame, split["sessions"], signal_start=dates[0],
                signal_end=dates[1], evaluation_end=dates[2],
                rules=_rules(backtest_raw), fee_config=fees,
                config=config, candidate_selector=selector)
            metrics = summarize_backtest(result.equity, result.trades,
                                         config.initial_capital)
            if result.equity["cash"].min() < -1e-7:
                raise AssertionError("negative cash in Strategy 2 backtest")
            if result.open_positions:
                raise AssertionError("evaluation tail ended with open positions")
            if abs(metrics["net_pnl"] - metrics["net_pnl_trades"]) > 1e-4:
                raise AssertionError("Strategy 2 trade ledger does not reconcile")
            rows.append({"split": name, "slippage_bps_per_side": bps, **metrics})
            if bps == float(full_raw["base_slippage_bps"]):
                result.equity.to_csv(output_dir / f"{name}_equity.csv", index=False)
                result.trades.to_csv(output_dir / f"{name}_trades.csv", index=False)
                result.orders.to_csv(output_dir / f"{name}_orders.csv", index=False)
        del frame
    summary_path = output_dir / "scenario_summary.csv"
    results = pd.DataFrame(rows)
    if summary_path.exists():
        previous = pd.read_csv(summary_path)
        previous = previous.loc[~previous["split"].isin(splits)]
        results = pd.concat([previous, results], ignore_index=True)
    results = results.sort_values(["split", "slippage_bps_per_side"])
    results.to_csv(summary_path, index=False)
    manifest = {
        "version": full_raw["version"],
        "test_status": "previously_viewed_exploratory_not_fresh_out_of_sample",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "feature_version": FEATURE_VERSION,
        **expected_hashes,
        "source_snapshot_sha256": _sha256(database.parent / "phase2-source-snapshot.duckdb"),
        "fee_profile": fees.profile,
        "splits": sorted(set(old_manifest.get("splits", [])) | set(splits)),
        "windows": {key: [str(date.date()) for date in split[key]]
                    for key in ("train", "validation", "test")},
    }
    previous_manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"manifest": manifest, "results": rows}

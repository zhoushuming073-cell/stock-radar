"""Chronological Strategy 2 portfolio research and frozen test runner."""

from __future__ import annotations

import hashlib
import json
import subprocess
from uuid import uuid4
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from radar.backtest.costs import load_fee_config
from radar.backtest.engine import BacktestConfig, BacktestResult, run_backtest
from radar.backtest.metrics import summarize_backtest
from radar.research.pipeline import FEATURE_VERSION
from radar.strategy.ranking import CandidateRules


def load_backtest_config(path: Path) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("backtest configuration must be a mapping")
    return raw


def split_dates(database: Path, research_config: Path) -> dict:
    cfg = yaml.safe_load(research_config.read_text(encoding="utf-8"))["research"]
    conn = duckdb.connect(str(database), read_only=True)
    try:
        sessions = [pd.Timestamp(row[0]) for row in conn.execute(
            "SELECT date FROM daily_bars WHERE symbol='SPY' ORDER BY date"
        ).fetchall()]
    finally:
        conn.close()
    n = len(sessions)
    train_end = int(n * cfg["train_fraction"])
    validation_end = int(n * (cfg["train_fraction"] + cfg["validation_fraction"]))
    embargo = int(cfg["embargo_sessions"])
    if embargo < int(cfg["max_forward_sessions"]) or validation_end + embargo >= n:
        raise ValueError("invalid split or embargo")
    return {
        "sessions": sessions,
        "train": (sessions[0], sessions[train_end - embargo - 1], sessions[train_end - 1]),
        "validation": (sessions[train_end + embargo],
                       sessions[validation_end - embargo - 1], sessions[validation_end - 1]),
        "test": (sessions[validation_end], sessions[n - embargo - 1], sessions[-1]),
        "test_start": sessions[validation_end],
    }


def load_segment(database: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    """Fetch only the requested segment; selection never loads Test bars."""
    conn = duckdb.connect(str(database), read_only=True)
    try:
        data = conn.execute("""
            SELECT f.date, f.symbol, b.open, b.close,
                   f.avg_dollar_volume_20, f.elasticity_score,
                   f.drawdown_20, f.ret_1, f.ret_60, f.close_location,
                   f.tradability_pass, a.name AS security_name
            FROM daily_features f
            JOIN daily_bars b ON f.date=b.date AND f.symbol=b.symbol
            JOIN assets a ON f.symbol=a.symbol
            WHERE f.feature_version=? AND f.date BETWEEN ? AND ?
        """, [FEATURE_VERSION, start.date(), end.date()]).df()
    finally:
        conn.close()
    if data.empty:
        raise ValueError(f"no research features between {start.date()} and {end.date()}")
    data["date"] = pd.to_datetime(data["date"])
    if data.duplicated(["date", "symbol"]).any():
        raise ValueError("duplicate feature rows for a date and symbol")
    return data.set_index(["date", "symbol"], drop=False).sort_index()


def load_spy_ma200_guard(database: Path, through: pd.Timestamp) -> dict[pd.Timestamp, bool]:
    """SPY close >= trailing 200-session mean, known at each signal close."""
    conn = duckdb.connect(str(database), read_only=True)
    try:
        spy = conn.execute("""
            SELECT date, close FROM daily_bars
            WHERE symbol='SPY' AND date<=? ORDER BY date
        """, [through.date()]).df()
    finally:
        conn.close()
    spy["date"] = pd.to_datetime(spy["date"])
    close = spy.set_index("date")["close"].astype(float)
    allowed = close.ge(close.rolling(200, min_periods=200).mean())
    return {date: bool(value) for date, value in allowed.items()}


def _rules(raw: dict) -> CandidateRules:
    trend = raw.get("exploratory_trend_reversal", {})
    return CandidateRules(
        elasticity_min=float(raw["elasticity_min"]),
        drawdown_20_max=float(raw["drawdown_20_max"]),
        max_new=int(raw["max_new_candidates"]),
        exclude_explicit_etf_etn_names=bool(raw["exclude_explicit_etf_etn_names"]),
        trend_elasticity_min=float(trend.get("elasticity_min", 60)),
        trend_ret_60_min=float(trend.get("ret_60_min", .037)),
        trend_drawdown_20_min=float(trend.get("drawdown_20_min", -.20)),
        trend_drawdown_20_max=float(trend.get("drawdown_20_max", -.05)),
        trend_close_location_min=float(trend.get("close_location_min", .5)),
    )


def _engine_config(raw: dict, *, variant: str, allocator: str,
                   slippage_bps: float, max_position_fraction: float,
                   market_guard: str = "none") -> BacktestConfig:
    return BacktestConfig(
        initial_capital=float(raw["initial_capital"]),
        take_profit=(None if raw["take_profit"] is None else float(raw["take_profit"])),
        stop_loss=(None if raw["stop_loss"] is None else float(raw["stop_loss"])),
        max_holding_sessions=(None if raw["max_holding_sessions"] is None
                              else int(raw["max_holding_sessions"])),
        entry_gap_min=float(raw["entry_gap_min"]),
        entry_gap_max=float(raw["entry_gap_max"]),
        max_position_fraction=float(max_position_fraction),
        minimum_position_fraction=float(raw["minimum_position_fraction"]),
        max_order_to_avg_dollar_volume=float(raw["max_order_to_avg_dollar_volume"]),
        slippage_bps=float(slippage_bps), allocator=allocator,
        candidate_variant=variant, market_guard=market_guard,
        execution_timing="legacy_close",  # Preserve the frozen Phase 2 runner contract.
    )


def run_one_segment(
    frame: pd.DataFrame, dates: tuple[pd.Timestamp, pd.Timestamp, pd.Timestamp],
    sessions: list[pd.Timestamp], raw: dict, fee_config,
    *, variant: str, allocator: str, slippage_bps: float,
    max_position_fraction: float, market_guard: str = "none",
    market_ok: dict[pd.Timestamp, bool] | None = None,
) -> tuple[BacktestResult, dict]:
    config = _engine_config(raw, variant=variant, allocator=allocator,
                            slippage_bps=slippage_bps,
                            max_position_fraction=max_position_fraction,
                            market_guard=market_guard)
    result = run_backtest(
        frame, sessions, signal_start=dates[0], signal_end=dates[1],
        evaluation_end=dates[2], rules=_rules(raw), fee_config=fee_config,
        config=config, market_ok=market_ok)
    metrics = summarize_backtest(result.equity, result.trades, config.initial_capital)
    metrics["open_positions_at_end"] = len(result.open_positions)
    metrics["missing_mark_days"] = int(result.equity["missing_marks"].sum())
    return result, metrics


def run_research_grid(
    database: Path, research_config: Path, backtest_config: Path, output_dir: Path,
) -> dict:
    """Run the small predeclared grid on Train and Validation; never read Test."""
    raw = load_backtest_config(backtest_config)
    fee_path = backtest_config.parents[1] / raw["fee_config"]
    fees = load_fee_config(fee_path)
    split = split_dates(database, research_config)
    output_dir.mkdir(parents=True, exist_ok=True)
    rows = []
    for name in ("train", "validation"):
        dates = split[name]
        frame = load_segment(database, dates[0], dates[2])
        for variant in raw["candidate_variants"]:
            for allocator in raw["allocator_variants"]:
                result, metrics = run_one_segment(
                    frame, dates, split["sessions"], raw, fees,
                    variant=variant, allocator=allocator,
                    slippage_bps=float(raw["base_slippage_bps"]),
                    max_position_fraction=float(raw["max_position_fraction"]))
                rows.append({"split": name, "candidate_variant": variant,
                             "allocator": allocator, "slippage_bps": raw["base_slippage_bps"],
                             "max_position_fraction": raw["max_position_fraction"],
                             **{key: value for key, value in metrics.items()
                                if not isinstance(value, dict)}})
                # The fixed combined/equal baseline gets a complete ledger.
                if variant == "combined_rank" and allocator == "equal_cash":
                    result.equity.to_csv(output_dir / f"{name}_baseline_equity.csv", index=False)
                    result.trades.to_csv(output_dir / f"{name}_baseline_trades.csv", index=False)
                    result.orders.to_csv(output_dir / f"{name}_baseline_orders.csv", index=False)
        del frame
    path = output_dir / "research_grid.csv"
    pd.DataFrame(rows).to_csv(path, index=False)
    return {"grid": str(path), "rows": len(rows),
            "train": [str(day.date()) for day in split["train"]],
            "validation": [str(day.date()) for day in split["validation"]],
            "test_first_day": str(split["test_start"].date()),
            "test_loaded": False,
            "backtest_config_hash": hashlib.sha256(backtest_config.read_bytes()).hexdigest(),
            "research_config_hash": hashlib.sha256(research_config.read_bytes()).hexdigest(),
            "fee_profile": fees.profile,
            "generated_at": datetime.now(timezone.utc).isoformat()}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def run_frozen_test(frozen_path: Path) -> dict:
    """Evaluate one immutable diagnostic strategy once on the sealed Test slice."""
    root = frozen_path.resolve().parents[1]
    frozen = yaml.safe_load(frozen_path.read_text(encoding="utf-8"))
    database = root / "data" / "phase2-research.duckdb"
    snapshot = root / "data" / "phase2-source-snapshot.duckdb"
    research_config = root / "config" / "research.yaml"
    backtest_config = root / "config" / "backtest.yaml"
    expected = {
        "research_config_sha256": _sha256(research_config),
        "backtest_config_sha256": _sha256(backtest_config),
        "source_snapshot_sha256": _sha256(snapshot),
    }
    for key, actual in expected.items():
        if frozen[key].lower() != actual.lower():
            raise ValueError(f"frozen {key} does not match current input")
    output_dir = root / "data" / "research" / "final-test-v1"
    marker = root / "data" / "research" / "test_evaluation_record.json"
    freeze_hash = _sha256(frozen_path)
    if marker.exists():
        existing = json.loads(marker.read_text(encoding="utf-8"))
        if existing.get("frozen_sha256") != freeze_hash:
            raise ValueError("the sealed Test was already evaluated under another frozen strategy")
        summary_path = output_dir / "backtest_summary.json"
        if summary_path.exists():
            return json.loads(summary_path.read_text(encoding="utf-8"))
        raise ValueError("Test marker exists but summary is incomplete; inspect the run")
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root,
                            capture_output=True, text=True, check=True).stdout.strip()
    if commit != frozen["simulation_commit"]:
        raise ValueError("simulation commit changed after the strategy was frozen")
    if subprocess.run(["git", "diff", "--quiet", "HEAD", "--", "src", "config/backtest.yaml",
                       "config/research.yaml"], cwd=root, check=False).returncode != 0:
        raise ValueError("simulation source or configuration has uncommitted changes")
    raw = load_backtest_config(backtest_config)
    if frozen["strategy_version"] != raw["strategy_version"]:
        raise ValueError("strategy version differs from frozen manifest")
    fees = load_fee_config(research_config)
    if frozen["fee_profile"] != fees.profile:
        raise ValueError("fee profile differs from frozen manifest")
    split = split_dates(database, research_config)
    dates = split["test"]
    frame = load_segment(database, dates[0], dates[2])
    result, metrics = run_one_segment(
        frame, dates, split["sessions"], raw, fees,
        variant=frozen["candidate_variant"], allocator=frozen["allocator"],
        slippage_bps=float(frozen["slippage_bps"]),
        max_position_fraction=float(frozen["max_position_fraction"]),
        market_guard=frozen["market_guard"],
        market_ok=(load_spy_ma200_guard(database, dates[2])
                   if frozen["market_guard"] == "spy_ma200" else None),
    )
    if result.open_positions:
        raise ValueError("Test ended with open positions; do not report a complete trade return")
    if result.equity["cash"].min() < -1e-7:
        raise AssertionError("negative cash in final Test")
    if abs(result.equity["equity"].iloc[-1] - float(raw["initial_capital"])
           - result.trades["net_pnl"].sum()) > 1e-6:
        raise AssertionError("trade ledger does not reconcile to ending equity")
    if not result.trades.empty:
        identity = (result.trades["gross_pnl"] - result.trades["buy_fee_total"]
                    - result.trades["sell_fee_total"] - result.trades["slippage_cost"]
                    - result.trades["net_pnl"])
        if identity.abs().max() > 1e-6:
            raise AssertionError("trade cost components do not reconcile")
    conn = duckdb.connect(str(database), read_only=True)
    try:
        spy = conn.execute("""
            SELECT date, close FROM daily_bars WHERE symbol='SPY'
              AND date IN (?, ?) ORDER BY date
        """, [dates[0].date(), dates[2].date()]).fetchall()
        latest_download = conn.execute("SELECT MAX(downloaded_at) FROM daily_bars").fetchone()[0]
    finally:
        conn.close()
    spy_return = spy[-1][1] / spy[0][1] - 1 if len(spy) == 2 else None
    manifest = {
        "run_id": str(uuid4()), "run_at_utc": datetime.now(timezone.utc).isoformat(),
        "simulation_commit": commit, **expected,
        "frozen_sha256": freeze_hash,
        "provider": "alpaca", "feed": "sip", "adjustment": "split",
        "latest_downloaded_at": str(latest_download),
        "feature_version": FEATURE_VERSION, "label_version": "open_close_v1",
        "strategy_version": frozen["strategy_version"],
        "fee_profile": fees.profile, "slippage_bps": frozen["slippage_bps"],
        "candidate_variant": frozen["candidate_variant"],
        "allocator": frozen["allocator"],
        "max_position_fraction": frozen["max_position_fraction"],
        "market_guard": frozen["market_guard"],
        "train": [str(day.date()) for day in split["train"]],
        "validation": [str(day.date()) for day in split["validation"]],
        "test": [str(day.date()) for day in dates],
        "test_runs_for_this_freeze": 1,
    }
    summary = {
        "status": "diagnostic_failed_candidate_not_for_deployment",
        "test": metrics, "spy_close_to_close_return_before_costs": spy_return,
        "cash_benchmark_return": 0.0,
        "manifest": manifest,
        "limitations": [
            "current-snapshot survivorship bias and imperfect security classification",
            "unconfirmed illustrative brokerage fee profile",
            "fixed-bps slippage excludes market impact",
            "this candidate failed Train and Validation stability checks before Test",
        ],
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    result.equity.to_csv(output_dir / "backtest_daily_equity.csv", index=False)
    result.trades.to_csv(output_dir / "backtest_trades.csv", index=False)
    result.orders.to_csv(output_dir / "backtest_orders.csv", index=False)
    (output_dir / "run_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    (output_dir / "backtest_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    marker.parent.mkdir(parents=True, exist_ok=True)
    marker.write_text(json.dumps({"frozen_sha256": freeze_hash, "run_id": manifest["run_id"]}),
                      encoding="utf-8")
    return summary

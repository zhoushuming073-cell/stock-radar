"""Freeze one bounded Q2 LEAN input bundle without invoking a portfolio backtest."""
from __future__ import annotations

import json
from pathlib import Path
from uuid import uuid4

import pandas as pd

from radar.backtest.costs import load_fee_config
from radar.backtest.runner import split_dates
from radar.lab.data import available_features
from radar.lab.manager import RunManager
from radar.lab.research_backend import FEATURES, ResearchHistory, load_execution_prices, load_signal_frame
from radar.lean.export import freeze_signals, prepare_bundle
from radar.lean.runtime import digest, installation
from radar.strategy.loader import load_strategy_directory


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    start, end, evaluation_end = "2024-10-01", "2024-10-01", "2024-10-15"
    manager = RunManager(root, store_path=root / "data/strategy-lab/q2-v13-input-preflight.sqlite3")
    registration = load_strategy_directory(
        root / "templates/q2_relaxed_channel_v1_3",
        available_features(root / "data/phase2-research.duckdb") | FEATURES, registry=manager.registry)
    metadata = manager._prepare_runs(
        ["q2_relaxed_channel_v1_3@1.3.0"], split="validation",
        window_override=(start, end, evaluation_end))[0]
    calendar = split_dates(root / "data/phase2-research.duckdb", root / "config/research.yaml")
    sessions = [day for day in calendar["sessions"]
                if pd.Timestamp(start) <= day <= pd.Timestamp(evaluation_end)]
    frame = load_signal_frame(root, pd.Timestamp(start), pd.Timestamp(end))
    execution = metadata["resolved_config"]["values"]["execution"]
    with ResearchHistory(root) as host:
        signals, allowed = freeze_signals(frame, sessions, metadata, registration.plugin,
                                          manager.store, execution, history=host.history)
    if not signals:
        raise ValueError("Q2 v1.3 preflight produced no signals")
    prices = load_execution_prices(root, frame, signals, start, evaluation_end)
    home, identity = installation(root)
    output = root / "data/strategy-lab/q2-v13-input-preflight" / str(uuid4())
    manifest = prepare_bundle(home, output, metadata, sessions, signals, prices, execution,
                              load_fee_config(root / "config/research.yaml"), allowed,
                              metadata["lean_max_positions"])
    bundle = json.loads(manifest.read_text(encoding="utf-8"))
    print(json.dumps({"engine": metadata["engine"], "lean_identity": identity,
                      "backend": metadata["universe_mode"],
                      "semantic_hash": metadata["research_backend"]["semantic_hash"],
                      "signal_count": len(signals), "price_rows": len(prices),
                      "max_new_positions_per_day": execution["max_new_positions_per_day"],
                      "max_simultaneous_positions": metadata["lean_max_positions"],
                      "max_holding_sessions": execution["exit"]["max_holding_sessions"],
                      "take_profit": execution["exit"]["take_profit"],
                      "stop_loss": execution["exit"]["stop_loss"],
                      "fee_profile": metadata["fee_profile"],
                      "slippage_bps": execution["slippage_bps"],
                      "manifest_sha256": digest(manifest),
                      "signal_snapshot": bundle["signal_snapshot"],
                      "lean_invoked": False, "portfolio_result_read": False},
                     indent=2, default=str))


if __name__ == "__main__":
    main()

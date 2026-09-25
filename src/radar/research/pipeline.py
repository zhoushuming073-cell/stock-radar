"""Build causal features and separate forward labels in a research database."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
from pathlib import Path
import subprocess
from uuid import uuid4

import duckdb
import pandas as pd

from radar.features.base import compute_base_features
from radar.features.elasticity import ElasticityConfig, compute_elasticity_inputs
from radar.features.scoring import load_research_config, tradability_gate
from radar.features.strategy2 import compute_strategy2_features
from radar.labels.forward import compute_forward_labels
from radar.schema import RESEARCH_COLUMNS, ensure_research_schema


FEATURE_VERSION = "phase2a_f_v2"
LABEL_VERSION = "open_close_v1"


def _read_bars(connection: duckdb.DuckDBPyConnection, symbol: str, sessions: pd.Index) -> pd.DataFrame:
    bars = connection.execute(
        "SELECT date, open, high, low, close, volume FROM daily_bars WHERE symbol = ? ORDER BY date",
        [symbol],
    ).df()
    if bars.empty:
        return pd.DataFrame(index=sessions, columns=["open", "high", "low", "close", "volume"], dtype=float)
    bars["date"] = pd.to_datetime(bars["date"])
    return bars.set_index("date").reindex(sessions)


def _replace_symbol_rows(connection: duckdb.DuckDBPyConnection, table: str,
                         symbol: str, version: str, frame: pd.DataFrame) -> None:
    version_col = "feature_version" if table == "daily_features" else "label_version"
    ordered = list(RESEARCH_COLUMNS[table])
    payload = frame.reindex(columns=ordered)
    connection.register("phase2_payload", payload)
    try:
        connection.execute("BEGIN TRANSACTION")
        connection.execute(f"DELETE FROM {table} WHERE symbol=? AND {version_col}=?", [symbol, version])
        columns = ", ".join(ordered)
        connection.execute(f"INSERT INTO {table} ({columns}) SELECT {columns} FROM phase2_payload")
        connection.execute("COMMIT")
    except Exception:
        connection.execute("ROLLBACK")
        raise
    finally:
        connection.unregister("phase2_payload")


def build_research_tables(
    database: Path, config_path: Path, *, max_symbols: int | None = None,
) -> dict[str, int | str]:
    """Build all selected symbols; dates are aligned to the SPY session calendar."""
    cfg = load_research_config(config_path)
    config_bytes = config_path.read_bytes()
    all_settings = __import__("yaml").safe_load(config_bytes)
    settings = all_settings["elasticity"]
    elasticity_cfg = ElasticityConfig(
        history_window=int(settings["history_window"]), history_min=int(settings["history_min"]),
        burst_quantile=float(settings["burst_quantile"]),
        hit_5_weight=float(settings["hit_5_weight"]), hit_10_weight=float(settings["hit_10_weight"]),
    )
    connection = duckdb.connect(str(database))
    try:
        ensure_research_schema(connection)
        spy = connection.execute("SELECT date, close FROM daily_bars WHERE symbol='SPY' ORDER BY date").df()
        qqq = connection.execute("SELECT date, close FROM daily_bars WHERE symbol='QQQ' ORDER BY date").df()
        if spy.empty or qqq.empty:
            raise ValueError("SPY and QQQ benchmark bars are required")
        spy["date"] = pd.to_datetime(spy["date"])
        qqq["date"] = pd.to_datetime(qqq["date"])
        spy_close = spy.set_index("date")["close"].astype(float)
        qqq_close = qqq.set_index("date")["close"].astype(float)
        sessions = spy_close.index
        research_cfg = all_settings["research"]
        train_end = int(len(sessions) * research_cfg["train_fraction"])
        validation_end = int(len(sessions) * (research_cfg["train_fraction"] + research_cfg["validation_fraction"]))
        embargo = int(research_cfg["embargo_sessions"])
        if embargo < int(research_cfg["max_forward_sessions"]):
            raise ValueError("embargo must cover the longest forward label")
        symbols = [r[0] for r in connection.execute("""
            WITH recent AS (
                SELECT symbol, AVG(close * volume) AS dollar_volume
                FROM daily_bars
                WHERE date >= (SELECT MAX(date) FROM daily_bars) - INTERVAL 35 DAY
                GROUP BY symbol
            )
            SELECT a.symbol FROM assets a
            JOIN recent r ON a.symbol=r.symbol
            WHERE a.symbol NOT IN ('SPY','QQQ')
              AND upper(trim(a.asset_class))='US_EQUITY'
              AND upper(trim(a.status))='ACTIVE'
              AND a.tradable
              AND upper(trim(a.exchange)) IN ('NASDAQ','NYSE','AMEX','ARCA','BATS')
            ORDER BY r.dollar_volume DESC NULLS LAST, a.symbol
        """).fetchall()]
        if max_symbols:
            symbols = symbols[:max_symbols]
        assets = {row[0]: (row[1], row[2]) for row in connection.execute(
            "SELECT symbol, tradable, exchange FROM assets"
        ).fetchall()}
        counts = {"symbols": 0, "feature_rows": 0, "label_rows": 0, "scored_rows": 0}
        for symbol in symbols:
            bars = _read_bars(connection, symbol, sessions)
            base = compute_base_features(bars)
            elastic = compute_elasticity_inputs(bars, spy_close, qqq_close, elasticity_cfg)
            strategy2 = compute_strategy2_features(bars, spy_close, qqq_close)
            feature = pd.concat([base, elastic, strategy2], axis=1)
            feature["elasticity_atr_raw"] = feature["atr_pct_20"]
            feature["symbol"] = symbol
            feature["date"] = sessions.date
            feature["feature_version"] = FEATURE_VERSION
            feature["computed_at"] = datetime.now(timezone.utc)
            observed = bars["close"].notna()
            tradable, exchange = assets.get(symbol, (False, None))
            gate_input = pd.DataFrame({
                "close": bars["close"],
                "avg_dollar_volume_20": feature["avg_dollar_volume_20"],
                "history_sessions": observed.cumsum(),
                "tradable": tradable, "exchange": exchange,
            }, index=sessions)
            feature["tradability_pass"] = tradability_gate(gate_input, cfg)
            feature = feature.loc[observed]
            _replace_symbol_rows(connection, "daily_features", symbol, FEATURE_VERSION, feature)
            counts["feature_rows"] += len(feature)

            # The final test slice is never passed to the label engine.
            labels = compute_forward_labels(bars.iloc[:validation_end])
            labels["symbol"] = symbol
            labels["signal_date"] = sessions[:validation_end].date
            labels["label_version"] = LABEL_VERSION
            labels = labels.loc[observed.iloc[:validation_end] &
                                (labels.index <= sessions[validation_end - embargo - 1])]
            _replace_symbol_rows(connection, "forward_labels", symbol, LABEL_VERSION, labels)
            counts["label_rows"] += len(labels)
            counts["symbols"] += 1

        # Do the normalization after all selected symbols are present. Exclude
        # stale versions and future dates from the same-date percentile ranks.
        if symbols:
            placeholders = ",".join("?" for _ in symbols)
            raw = connection.execute(f"""
                SELECT symbol, date, elasticity_beta_raw, elasticity_atr_raw,
                       elasticity_idio_raw, elasticity_burst_raw, elasticity_hit_raw
                FROM daily_features WHERE feature_version=? AND symbol IN ({placeholders})
            """, [FEATURE_VERSION, *symbols]).df()
            from radar.features.scoring import COMPONENT_NAMES, score_elasticity
            scored = score_elasticity(raw, cfg)
            score_cols = ["symbol", "date", *[f"elasticity_{COMPONENT_NAMES[name]}_component" for name in cfg.weights], "elasticity_score"]
            connection.register("phase2_scores", scored[score_cols])
            try:
                assignments = ", ".join(f"{name}=s.{name}" for name in score_cols[2:])
                connection.execute(f"""
                    UPDATE daily_features AS f SET {assignments}
                    FROM phase2_scores AS s
                    WHERE f.symbol=s.symbol AND f.date=s.date AND f.feature_version=?
                """, [FEATURE_VERSION])
            finally:
                connection.unregister("phase2_scores")
            counts["scored_rows"] = int(scored["elasticity_score"].notna().sum())
        git_root = config_path.resolve().parents[1]
        commit_result = subprocess.run(["git", "rev-parse", "HEAD"], cwd=git_root,
                                       capture_output=True, text=True, check=False)
        status_result = subprocess.run(["git", "status", "--porcelain"], cwd=git_root,
                                       capture_output=True, text=True, check=False)
        git_commit = commit_result.stdout.strip() if commit_result.returncode == 0 else "unknown"
        if status_result.stdout.strip():
            git_commit += "-dirty"
        snapshot = connection.execute("SELECT MAX(downloaded_at) FROM daily_bars").fetchone()[0]
        run_id = str(uuid4())
        connection.execute("""
            INSERT INTO research_runs VALUES (?, ?, ?, ?, 'alpaca', 'sip', 'split',
                ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, [
            run_id, datetime.now(timezone.utc), git_commit, snapshot,
            FEATURE_VERSION, LABEL_VERSION,
            hashlib.sha256(config_bytes).hexdigest(),
            sessions[0].date(), sessions[train_end - 1].date(),
            sessions[train_end].date(), sessions[validation_end - 1].date(),
            sessions[validation_end].date(), sessions[-1].date(),
            f"built_a_f_{len(symbols)}_symbols",
        ])
        counts["run_id"] = run_id
        counts["database"] = str(database)
        return counts
    finally:
        connection.close()

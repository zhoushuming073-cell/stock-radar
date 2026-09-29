"""Build causal features and separate forward labels in a research database."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
from typing import Callable
from uuid import uuid4

import duckdb
import pandas as pd

from radar.features.base import compute_base_features
from radar.features.elasticity import ElasticityConfig, compute_elasticity_inputs
from radar.features.scoring import load_research_config, tradability_gate
from radar.features.strategy2 import compute_strategy2_features
from radar.labels.forward import compute_forward_labels
from radar.schema import RESEARCH_COLUMNS, ensure_research_schema
from radar.research.splits import resolve_split_windows


BUILD_FEATURE_VERSION = "phase2a_f_v3_asof"
FEATURE_VERSION = BUILD_FEATURE_VERSION
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


def _build_research_tables_in_place(
    database: Path, config_path: Path, *, max_symbols: int | None = None,
    progress: Callable[[dict], None] | None = None,
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
        # Keep the long full-cohort build within a desktop memory budget;
        # DuckDB spills large joins/sorts into its database temp directory.
        connection.execute("SET memory_limit='2GB'")
        connection.execute("SET threads=2")
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
        windows = resolve_split_windows(sessions, research_cfg)
        validation_end = sessions.get_loc(windows["validation"][2]) + 1
        # The current survivor cohort is an acknowledged limitation. Never
        # select its historical members using end-of-sample liquidity.
        symbols = [r[0] for r in connection.execute("""
            SELECT a.symbol FROM assets a
            WHERE a.symbol NOT IN ('SPY','QQQ')
              AND upper(trim(a.asset_class))='US_EQUITY'
              AND upper(trim(a.status))='ACTIVE'
              AND EXISTS (SELECT 1 FROM daily_bars b WHERE b.symbol=a.symbol)
            ORDER BY a.symbol
        """).fetchall()]
        cohort_total = len(symbols)
        if max_symbols:
            symbols = symbols[:max_symbols]
        # This connection is to a private staging DB. Clear prior same-version
        # rows there so changing cohorts cannot leave stale features or labels.
        connection.execute("DELETE FROM daily_features WHERE feature_version=?",
                           [BUILD_FEATURE_VERSION])
        connection.execute("DELETE FROM forward_labels WHERE label_version=?",
                           [LABEL_VERSION])
        counts = {"symbols": 0, "feature_rows": 0, "label_rows": 0,
                  "scored_rows": 0, "cohort_total": cohort_total,
                  "cohort_complete": max_symbols is None or max_symbols >= cohort_total}
        for symbol in symbols:
            bars = _read_bars(connection, symbol, sessions)
            base = compute_base_features(bars)
            elastic = compute_elasticity_inputs(bars, spy_close, qqq_close, elasticity_cfg)
            strategy2 = compute_strategy2_features(bars, spy_close, qqq_close)
            feature = pd.concat([base, elastic, strategy2], axis=1)
            feature["elasticity_atr_raw"] = feature["atr_pct_20"]
            feature["symbol"] = symbol
            feature["date"] = sessions.date
            feature["feature_version"] = BUILD_FEATURE_VERSION
            feature["computed_at"] = datetime.now(timezone.utc)
            observed = bars["close"].notna()
            gate_input = pd.DataFrame({
                "close": bars["close"],
                "avg_dollar_volume_20": feature["avg_dollar_volume_20"],
                "history_sessions": observed.cumsum(),
            }, index=sessions)
            feature["tradability_pass"] = tradability_gate(gate_input, cfg)
            feature = feature.loc[observed]
            _replace_symbol_rows(connection, "daily_features", symbol, BUILD_FEATURE_VERSION, feature)
            counts["feature_rows"] += len(feature)

            # The final test slice is never passed to the label engine.
            labels = compute_forward_labels(bars.iloc[:validation_end])
            labels["symbol"] = symbol
            labels["signal_date"] = sessions[:validation_end].date
            labels["label_version"] = LABEL_VERSION
            labels = labels.loc[observed.iloc[:validation_end] &
                                (labels.index <= windows["validation"][1])]
            _replace_symbol_rows(connection, "forward_labels", symbol, LABEL_VERSION, labels)
            counts["label_rows"] += len(labels)
            counts["symbols"] += 1
            if progress and (counts["symbols"] % 250 == 0 or
                             counts["symbols"] == len(symbols)):
                progress({"phase": "features", "completed": counts["symbols"],
                          "total": len(symbols)})

        # Do the normalization after all selected symbols are present. Exclude
        # stale versions and future dates from the same-date percentile ranks.
        if symbols:
            from radar.features.scoring import COMPONENT_NAMES, score_elasticity
            score_cols = ["symbol", "date", *[f"elasticity_{COMPONENT_NAMES[name]}_component" for name in cfg.weights], "elasticity_score"]
            assignments = ", ".join(f"{name}=s.{name}" for name in score_cols[2:])
            # A full cohort can contain millions of rows. Month-sized chunks
            # preserve same-day ranks without a multi-GB DataFrame.
            for offset in range(0, len(sessions), 20):
                first = sessions[offset].date()
                last = sessions[min(offset + 20, len(sessions)) - 1].date()
                raw = connection.execute("""
                    SELECT symbol, date, elasticity_beta_raw, elasticity_atr_raw,
                           elasticity_idio_raw, elasticity_burst_raw, elasticity_hit_raw
                    FROM daily_features WHERE feature_version=? AND tradability_pass
                      AND date BETWEEN ? AND ?
                """, [BUILD_FEATURE_VERSION, first, last]).df()
                if raw.empty:
                    continue
                scored = score_elasticity(raw, cfg)
                connection.register("phase2_scores", scored[score_cols])
                try:
                    connection.execute(f"""
                        UPDATE daily_features AS f SET {assignments}
                        FROM phase2_scores AS s
                        WHERE f.symbol=s.symbol AND f.date=s.date AND f.feature_version=?
                          AND f.date BETWEEN ? AND ?
                    """, [BUILD_FEATURE_VERSION, first, last])
                finally:
                    connection.unregister("phase2_scores")
                counts["scored_rows"] += int(scored["elasticity_score"].notna().sum())
                if progress:
                    progress({"phase": "scores", "completed_sessions": min(offset + 20, len(sessions)),
                              "total_sessions": len(sessions)})
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
            BUILD_FEATURE_VERSION, LABEL_VERSION,
            hashlib.sha256(config_bytes).hexdigest(),
            windows["train"][0].date(), windows["train"][2].date(),
            windows["validation"][0].date(), windows["validation"][2].date(),
            windows["test"][0].date(), windows["test"][2].date(),
            f"built_asof_{len(symbols)}_of_{cohort_total}_symbols",
        ])
        counts["run_id"] = run_id
        counts["database"] = str(database)
        return counts
    finally:
        connection.close()


def _validate_staging_store(database: Path, counts: dict, version: str) -> None:
    """Cheap full-cohort gates before the file can become the active store."""
    if not counts["cohort_complete"] or counts["symbols"] != counts["cohort_total"]:
        raise ValueError("partial research build cannot be promoted")
    with duckdb.connect(str(database), read_only=True) as connection:
        feature_count, symbol_count = connection.execute("""
            SELECT COUNT(*), COUNT(DISTINCT symbol) FROM daily_features
            WHERE feature_version=?
        """, [version]).fetchone()
        if feature_count != counts["feature_rows"] or symbol_count != counts["cohort_total"]:
            raise ValueError("staging feature rows do not match the completed cohort")
        label_count = connection.execute("""
            SELECT COUNT(*) FROM forward_labels WHERE label_version=?
        """, [LABEL_VERSION]).fetchone()[0]
        if label_count != counts["label_rows"]:
            raise ValueError("staging label rows do not match the completed build")
        missing = connection.execute("""
            SELECT COUNT(*) FROM daily_bars AS spy
            WHERE spy.symbol='SPY' AND NOT EXISTS (
                SELECT 1 FROM daily_features AS f
                WHERE f.feature_version=? AND f.date=spy.date)
        """, [version]).fetchone()[0]
        if missing:
            raise ValueError(f"staging store has {missing} uncovered SPY sessions")
        status = connection.execute("""
            SELECT status FROM research_runs WHERE run_id=? AND feature_version=?
        """, [counts["run_id"], version]).fetchone()
        expected = f"built_asof_{counts['cohort_total']}_of_{counts['cohort_total']}_symbols"
        if status is None or status[0] != expected:
            raise ValueError("staging store lacks a completed full-cohort build record")


def build_research_tables(
    database: Path, config_path: Path, *, max_symbols: int | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict[str, int | str]:
    """Build in a separate DB; publish the validated file with one atomic replace.

    A partial build is discarded. An interrupted build never touches the active
    database. A complete previous database is copied to research-backups before
    the replace, so a failed promotion leaves the original active file intact.
    """
    database = Path(database).resolve()
    if not database.is_file():
        raise FileNotFoundError(database)
    if max_symbols is not None and max_symbols < 1:
        raise ValueError("max_symbols must be positive")
    stage = database.with_name(f".{database.stem}.{uuid4().hex}.staging.duckdb")
    source_stat = database.stat()
    config_hash = hashlib.sha256(config_path.read_bytes()).hexdigest()
    keep_stage = False
    try:
        if progress:
            progress({"phase": "staging_copy", "source": str(database)})
        shutil.copy2(database, stage)
        counts = _build_research_tables_in_place(
            stage, config_path, max_symbols=max_symbols, progress=progress)
        counts["database"] = str(database)
        if not counts["cohort_complete"]:
            counts["promoted"] = False
            return counts
        _validate_staging_store(stage, counts, BUILD_FEATURE_VERSION)
        current_stat = database.stat()
        if (current_stat.st_size, current_stat.st_mtime_ns) != (
                source_stat.st_size, source_stat.st_mtime_ns):
            raise ValueError("active research store changed during staged build")
        if hashlib.sha256(config_path.read_bytes()).hexdigest() != config_hash:
            raise ValueError("research config changed during staged build")
        backup_dir = database.parent / "research-backups"
        backup_dir.mkdir(exist_ok=True)
        backup = backup_dir / f"{database.stem}.{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.{uuid4().hex[:8]}.duckdb"
        shutil.copy2(database, backup)
        try:
            os.replace(stage, database)
        except OSError:
            keep_stage = True
            raise RuntimeError(f"promotion failed; active store is unchanged; validated staging DB: {stage}") from None
        counts["promoted"] = True
        counts["backup_database"] = str(backup)
        return counts
    finally:
        if stage.exists() and not keep_stage:
            # The temporary filename is created next to the explicitly named
            # database; never remove any path outside that directory.
            if stage.resolve().parent != database.resolve().parent:
                raise RuntimeError("staging cleanup path escaped the database directory")
            stage.unlink()

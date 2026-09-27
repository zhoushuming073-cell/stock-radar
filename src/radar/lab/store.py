"""SQLite WAL store for immutable backtest Runs and live worker progress.

Market data remains in read-only DuckDB; this database contains Run metadata,
results, progress and events only. Each method opens its own SQLite connection
so a dashboard and worker can safely use separate processes.
"""

from __future__ import annotations

import json
import hashlib
import math
import sqlite3
import uuid
from contextlib import contextmanager
from dataclasses import asdict, is_dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterator, Mapping

import pandas as pd


SCHEMA_VERSION = 4
_TERMINAL = frozenset({"completed", "failed", "cancelled"})
_STATUSES = frozenset({"queued", "running", "cancel_requested", *_TERMINAL})
_REQUIRED_METADATA = frozenset({
    "strategy_id", "strategy_version", "plugin_interface_version",
    "strategy_path", "strategy_code_hash", "config", "config_hash",
    "git_revision", "feature_version", "data_snapshot", "source_watermark",
    "fee_profile", "slippage_bps", "execution_policy",
    "backtest_config_hash", "research_config_hash", "start_date", "end_date",
    "evaluation_end", "split", "window",
})


class RunStoreError(ValueError):
    """Invalid Run state transition, payload or identifier."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _jsonable(value: Any) -> Any:
    if value is pd.NA or value is pd.NaT:
        return None
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, (datetime, date, pd.Timestamp)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, Mapping):
        if not all(isinstance(key, str) for key in value):
            raise RunStoreError("JSON object keys must be strings")
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if is_dataclass(value) and not isinstance(value, type):
        return _jsonable(asdict(value))
    if hasattr(value, "item") and callable(value.item):
        return _jsonable(value.item())
    raise RunStoreError(f"value is not JSON serializable: {type(value).__name__}")


def _json(value: Any, *, sort_keys: bool = True) -> str:
    return json.dumps(_jsonable(value), ensure_ascii=False, sort_keys=sort_keys,
                      separators=(",", ":"), allow_nan=False)


def _rows(value: Any, label: str) -> list[dict[str, Any]]:
    if value is None:
        return []
    if isinstance(value, pd.DataFrame):
        value = value.to_dict(orient="records")
    if not isinstance(value, (list, tuple)) or not all(isinstance(row, Mapping) for row in value):
        raise RunStoreError(f"{label} must be a DataFrame or list of mappings")
    return [_jsonable(dict(row)) for row in value]


class RunStore:
    def __init__(self, path: str | Path) -> None:
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            version = int(connection.execute("PRAGMA user_version").fetchone()[0])
            if version > SCHEMA_VERSION:
                raise RunStoreError(
                    f"Run store schema {version} is newer than supported {SCHEMA_VERSION}"
                )
            if version == 0:
                self._migrate_v1(connection)
                version = 1
            if version == 1:
                self._migrate_v2(connection)
                version = 2
            if version == 2:
                self._migrate_v3(connection)
                version = 3
            if version == 3:
                self._migrate_v4(connection)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(str(self.path), timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        try:
            yield connection
        finally:
            connection.close()

    @staticmethod
    def _migrate_v1(connection: sqlite3.Connection) -> None:
        try:
            connection.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE backtest_runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK(status IN
                        ('queued','running','cancel_requested','completed','failed','cancelled')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    cancel_requested_at TEXT,
                    pid INTEGER,
                    metadata_json TEXT NOT NULL,
                    progress_json TEXT,
                    metrics_json TEXT,
                    result_json TEXT,
                    error_text TEXT
                );
                CREATE INDEX idx_runs_created ON backtest_runs(created_at DESC, run_id DESC);
                CREATE INDEX idx_runs_status ON backtest_runs(status, created_at DESC);
                CREATE TABLE equity (
                    run_id TEXT NOT NULL REFERENCES backtest_runs(run_id),
                    seq INTEGER NOT NULL,
                    row_json TEXT NOT NULL,
                    PRIMARY KEY(run_id, seq)
                );
                CREATE TABLE trades (
                    run_id TEXT NOT NULL REFERENCES backtest_runs(run_id),
                    seq INTEGER NOT NULL,
                    row_json TEXT NOT NULL,
                    PRIMARY KEY(run_id, seq)
                );
                CREATE TABLE events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    run_id TEXT NOT NULL REFERENCES backtest_runs(run_id),
                    at TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    payload_json TEXT NOT NULL
                );
                CREATE INDEX idx_events_run ON events(run_id, event_id);
                CREATE TRIGGER completed_run_update BEFORE UPDATE ON backtest_runs
                WHEN OLD.status = 'completed'
                BEGIN SELECT RAISE(ABORT, 'completed run is immutable'); END;
                CREATE TRIGGER completed_run_delete BEFORE DELETE ON backtest_runs
                WHEN OLD.status = 'completed'
                BEGIN SELECT RAISE(ABORT, 'completed run is immutable'); END;
                CREATE TRIGGER completed_equity_insert BEFORE INSERT ON equity
                WHEN (SELECT status FROM backtest_runs WHERE run_id=NEW.run_id) = 'completed'
                BEGIN SELECT RAISE(ABORT, 'completed equity is immutable'); END;
                CREATE TRIGGER completed_equity_update BEFORE UPDATE ON equity
                WHEN (SELECT status FROM backtest_runs WHERE run_id=OLD.run_id) = 'completed'
                  OR (SELECT status FROM backtest_runs WHERE run_id=NEW.run_id) = 'completed'
                BEGIN SELECT RAISE(ABORT, 'completed equity is immutable'); END;
                CREATE TRIGGER completed_equity_delete BEFORE DELETE ON equity
                WHEN (SELECT status FROM backtest_runs WHERE run_id=OLD.run_id) = 'completed'
                BEGIN SELECT RAISE(ABORT, 'completed equity is immutable'); END;
                CREATE TRIGGER completed_trades_insert BEFORE INSERT ON trades
                WHEN (SELECT status FROM backtest_runs WHERE run_id=NEW.run_id) = 'completed'
                BEGIN SELECT RAISE(ABORT, 'completed trades are immutable'); END;
                CREATE TRIGGER completed_trades_update BEFORE UPDATE ON trades
                WHEN (SELECT status FROM backtest_runs WHERE run_id=OLD.run_id) = 'completed'
                  OR (SELECT status FROM backtest_runs WHERE run_id=NEW.run_id) = 'completed'
                BEGIN SELECT RAISE(ABORT, 'completed trades are immutable'); END;
                CREATE TRIGGER completed_trades_delete BEFORE DELETE ON trades
                WHEN (SELECT status FROM backtest_runs WHERE run_id=OLD.run_id) = 'completed'
                BEGIN SELECT RAISE(ABORT, 'completed trades are immutable'); END;
                CREATE TRIGGER completed_events_insert BEFORE INSERT ON events
                WHEN (SELECT status FROM backtest_runs WHERE run_id=NEW.run_id) = 'completed'
                BEGIN SELECT RAISE(ABORT, 'completed events are immutable'); END;
                CREATE TRIGGER completed_events_update BEFORE UPDATE ON events
                WHEN (SELECT status FROM backtest_runs WHERE run_id=OLD.run_id) = 'completed'
                  OR (SELECT status FROM backtest_runs WHERE run_id=NEW.run_id) = 'completed'
                BEGIN SELECT RAISE(ABORT, 'completed events are immutable'); END;
                CREATE TRIGGER completed_events_delete BEFORE DELETE ON events
                WHEN (SELECT status FROM backtest_runs WHERE run_id=OLD.run_id) = 'completed'
                BEGIN SELECT RAISE(ABORT, 'completed events are immutable'); END;
                PRAGMA user_version=1;
                COMMIT;
            """)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _migrate_v2(connection: sqlite3.Connection) -> None:
        """Guard child UPDATEs that move rows into a completed Run."""
        try:
            connection.executescript("""
                BEGIN IMMEDIATE;
                DROP TRIGGER completed_equity_update;
                DROP TRIGGER completed_trades_update;
                DROP TRIGGER completed_events_update;
                CREATE TRIGGER completed_equity_update BEFORE UPDATE ON equity
                WHEN (SELECT status FROM backtest_runs WHERE run_id=OLD.run_id) = 'completed'
                  OR (SELECT status FROM backtest_runs WHERE run_id=NEW.run_id) = 'completed'
                BEGIN SELECT RAISE(ABORT, 'completed equity is immutable'); END;
                CREATE TRIGGER completed_trades_update BEFORE UPDATE ON trades
                WHEN (SELECT status FROM backtest_runs WHERE run_id=OLD.run_id) = 'completed'
                  OR (SELECT status FROM backtest_runs WHERE run_id=NEW.run_id) = 'completed'
                BEGIN SELECT RAISE(ABORT, 'completed trades are immutable'); END;
                CREATE TRIGGER completed_events_update BEFORE UPDATE ON events
                WHEN (SELECT status FROM backtest_runs WHERE run_id=OLD.run_id) = 'completed'
                  OR (SELECT status FROM backtest_runs WHERE run_id=NEW.run_id) = 'completed'
                BEGIN SELECT RAISE(ABORT, 'completed events are immutable'); END;
                PRAGMA user_version=2;
                COMMIT;
            """)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _migrate_v3(connection: sqlite3.Connection) -> None:
        try:
            connection.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE IF NOT EXISTS scanner_runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL CHECK(status IN ('queued','running','completed','failed')),
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    started_at TEXT,
                    finished_at TEXT,
                    pid INTEGER,
                    metadata_json TEXT NOT NULL,
                    progress_json TEXT,
                    metrics_json TEXT,
                    artifact_hashes_json TEXT,
                    error_text TEXT
                );
                CREATE INDEX IF NOT EXISTS idx_scanner_runs_created ON scanner_runs(created_at DESC,run_id DESC);
                CREATE TABLE IF NOT EXISTS scanner_candidates (
                    run_id TEXT NOT NULL REFERENCES scanner_runs(run_id),
                    signal_date TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    security_name TEXT,
                    rank INTEGER NOT NULL,
                    strategy_score REAL NOT NULL,
                    selected INTEGER NOT NULL CHECK(selected IN (0,1)),
                    diagnostics_json TEXT NOT NULL,
                    probabilities_json TEXT NOT NULL,
                    labels_json TEXT,
                    market_context_json TEXT NOT NULL,
                    PRIMARY KEY(run_id,signal_date,symbol)
                );
                CREATE INDEX IF NOT EXISTS idx_scanner_candidate_rank ON scanner_candidates(run_id,signal_date,rank);
                CREATE TRIGGER IF NOT EXISTS scanner_completed_update BEFORE UPDATE ON scanner_runs
                    WHEN OLD.status='completed'
                    BEGIN SELECT RAISE(ABORT,'completed scanner run is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS scanner_completed_delete BEFORE DELETE ON scanner_runs
                    WHEN OLD.status='completed'
                    BEGIN SELECT RAISE(ABORT,'completed scanner run is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS scanner_candidate_completed_insert BEFORE INSERT ON scanner_candidates
                    WHEN (SELECT status FROM scanner_runs WHERE run_id=NEW.run_id)='completed'
                    BEGIN SELECT RAISE(ABORT,'completed candidate snapshot is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS scanner_candidate_completed_update BEFORE UPDATE ON scanner_candidates
                    WHEN (SELECT status FROM scanner_runs WHERE run_id=OLD.run_id)='completed'
                      OR (SELECT status FROM scanner_runs WHERE run_id=NEW.run_id)='completed'
                    BEGIN SELECT RAISE(ABORT,'completed candidate snapshot is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS scanner_candidate_completed_delete BEFORE DELETE ON scanner_candidates
                    WHEN (SELECT status FROM scanner_runs WHERE run_id=OLD.run_id)='completed'
                    BEGIN SELECT RAISE(ABORT,'completed candidate snapshot is immutable'); END;
                PRAGMA user_version=3;
                COMMIT;
            """)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _migrate_v4(connection: sqlite3.Connection) -> None:
        try:
            connection.executescript("""
                BEGIN IMMEDIATE;
                ALTER TABLE scanner_candidates ADD COLUMN features_json TEXT NOT NULL DEFAULT '{}';
                PRAGMA user_version=4;
                COMMIT;
            """)
        except Exception:
            if connection.in_transaction:
                connection.execute("ROLLBACK")
            raise

    def create_scanner_run(self, metadata: Mapping[str, Any]) -> str:
        required = {"strategy_id", "strategy_version", "plugin_interface_version", "config",
                    "selection", "evaluation", "feature_version", "market_feature_version",
                    "data_snapshot", "source_watermark", "git_revision", "signal_start",
                    "signal_end", "label_version", "strategy_code_hash", "config_hash"}
        if not isinstance(metadata, Mapping) or required - set(metadata):
            raise RunStoreError(f"scanner metadata missing fields: {sorted(required - set(metadata))}")
        run_id, now = str(uuid.uuid4()), _now()
        with self._connect() as connection:
            connection.execute("INSERT INTO scanner_runs(run_id,status,created_at,updated_at,metadata_json) "
                               "VALUES (?,?,?,?,?)", (run_id, "queued", now, now, _json(metadata)))
        return run_id

    def start_scanner_run(self, run_id: str, pid: int) -> None:
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise RunStoreError("pid must be positive")
        with self._connect() as connection:
            now = _now()
            changed = connection.execute("UPDATE scanner_runs SET status='running',pid=?,started_at=?,"
                                         "updated_at=? WHERE run_id=? AND status='queued'",
                                         (pid, now, now, run_id)).rowcount
            if changed != 1:
                raise RunStoreError("scanner run is not queued")

    def scanner_progress(self, run_id: str, progress: Mapping[str, Any]) -> None:
        with self._connect() as connection:
            changed = connection.execute("UPDATE scanner_runs SET progress_json=?,updated_at=? "
                                         "WHERE run_id=? AND status='running'",
                                         (_json(progress), _now(), run_id)).rowcount
            if changed != 1:
                raise RunStoreError("scanner run is not running")

    def finish_scanner_run(self, run_id: str, candidates: list[Mapping[str, Any]],
                           metrics: Mapping[str, Any]) -> None:
        source_rows = _rows(candidates, "candidates")
        rows = sorted(({
            "signal_date": str(row["signal_date"])[:10],
            "symbol": str(row["symbol"]),
            "security_name": row.get("security_name"),
            "rank": int(row["rank"]),
            "strategy_score": float(row["strategy_score"]),
            "selected": bool(row["selected"]),
            "diagnostics": row.get("diagnostics", {}),
            "probabilities": row.get("probabilities", {}),
            "label": row.get("label"),
            "market_context": row.get("market_context", {}),
            "features": row.get("features", {}),
        } for row in source_rows), key=lambda row: (row["signal_date"], row["rank"], row["symbol"]))
        canonical = _json(rows).encode("utf-8")
        metrics_json = _json(metrics)
        hashes = {"format": "scanner-candidates-v2",
                  "candidates_sha256": hashlib.sha256(canonical).hexdigest(),
                  "metrics_sha256": hashlib.sha256(metrics_json.encode("utf-8")).hexdigest()}
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                status = connection.execute("SELECT status FROM scanner_runs WHERE run_id=?",
                                            (run_id,)).fetchone()
                if status is None or status["status"] != "running":
                    raise RunStoreError("scanner run is not running")
                connection.executemany("""
                    INSERT INTO scanner_candidates
                    (run_id,signal_date,symbol,security_name,rank,strategy_score,selected,
                     diagnostics_json,probabilities_json,labels_json,market_context_json,features_json)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
                """, ((run_id, row["signal_date"], row["symbol"],
                       row["security_name"], row["rank"], row["strategy_score"],
                       int(row["selected"]), _json(row["diagnostics"]),
                       _json(row["probabilities"]),
                       _json(row["label"]) if row.get("label") is not None else None,
                       _json(row["market_context"]), _json(row["features"])) for row in rows))
                now = _now()
                connection.execute("UPDATE scanner_runs SET status='completed',metrics_json=?,"
                                   "artifact_hashes_json=?,finished_at=?,updated_at=? WHERE run_id=?",
                                   (metrics_json, _json(hashes), now, now, run_id))
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def fail_scanner_run(self, run_id: str, error: str) -> None:
        with self._connect() as connection:
            now = _now()
            connection.execute("UPDATE scanner_runs SET status='failed',error_text=?,"
                               "finished_at=?,updated_at=? WHERE run_id=? AND status IN ('queued','running')",
                               (str(error), now, now, run_id))

    @staticmethod
    def _scanner_dict(row: sqlite3.Row) -> dict[str, Any]:
        result = dict(row)
        for column, key in (("metadata_json", "metadata"), ("progress_json", "progress"),
                            ("metrics_json", "metrics"), ("artifact_hashes_json", "artifact_hashes")):
            raw = result.pop(column)
            result[key] = json.loads(raw) if raw is not None else None
        return result

    def list_scanner_runs(self, limit: int = 100) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10000:
            raise RunStoreError("invalid scanner run limit")
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM scanner_runs ORDER BY created_at DESC,run_id DESC "
                                      "LIMIT ?", (limit,)).fetchall()
        return [self._scanner_dict(row) for row in rows]

    def get_scanner_run(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute("SELECT * FROM scanner_runs WHERE run_id=?", (run_id,)).fetchone()
        if row is None:
            raise RunStoreError(f"unknown scanner run: {run_id}")
        return self._scanner_dict(row)

    def get_scanner_candidates(self, run_id: str, *, limit: int = 10000,
                               max_rank: int | None = None,
                               signal_date: str | None = None) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10_000_000:
            raise RunStoreError("invalid candidate limit")
        if max_rank is not None and (isinstance(max_rank, bool) or not isinstance(max_rank, int)
                                     or not 1 <= max_rank <= 100000):
            raise RunStoreError("invalid candidate rank limit")
        if signal_date is not None and (len(signal_date) != 10 or
                                        pd.isna(pd.to_datetime(signal_date, errors="coerce"))):
            raise RunStoreError("invalid signal date")
        clauses = ["run_id=?"]
        parameters: list[Any] = [run_id]
        if max_rank is not None:
            clauses.append("rank<=?")
            parameters.append(max_rank)
        if signal_date is not None:
            clauses.append("signal_date=?")
            parameters.append(signal_date)
        parameters.append(limit)
        with self._connect() as connection:
            rows = connection.execute("SELECT * FROM scanner_candidates WHERE " +
                                      " AND ".join(clauses) +
                                      " ORDER BY signal_date,rank LIMIT ?", parameters).fetchall()
        return [{"signal_date": row["signal_date"], "symbol": row["symbol"],
                 "security_name": row["security_name"], "rank": row["rank"],
                 "strategy_score": row["strategy_score"], "selected": bool(row["selected"]),
                 "diagnostics": json.loads(row["diagnostics_json"]),
                 "probabilities": json.loads(row["probabilities_json"]),
                 "label": json.loads(row["labels_json"]) if row["labels_json"] else None,
                 "market_context": json.loads(row["market_context_json"]),
                 "features": json.loads(row["features_json"])} for row in rows]

    def verify_scanner_artifacts(self, run_id: str) -> bool:
        """Recompute saved hashes, including the two early v1.5 snapshot formats."""
        run = self.get_scanner_run(run_id)
        if run["status"] != "completed" or not run["artifact_hashes"]:
            return False
        expected = run["artifact_hashes"]
        count = int((run.get("metrics") or {}).get("candidate_count", 0))
        rows = self.get_scanner_candidates(run_id, limit=max(1, count))
        if len(rows) != count:
            return False
        candidates_hash = hashlib.sha256(_json(rows).encode("utf-8")).hexdigest()
        if candidates_hash != expected["candidates_sha256"] and not expected.get("format"):
            legacy = [{**row, "signal_date": row["signal_date"] + "T00:00:00"}
                      for row in rows]
            candidates_hash = hashlib.sha256(_json(legacy).encode("utf-8")).hexdigest()
            if candidates_hash != expected["candidates_sha256"]:
                without_features = [{key: value for key, value in row.items()
                                     if key != "features"} for row in legacy]
                candidates_hash = hashlib.sha256(
                    _json(without_features).encode("utf-8")).hexdigest()
        metrics_hash = hashlib.sha256(_json(run["metrics"]).encode("utf-8")).hexdigest()
        return (candidates_hash == expected["candidates_sha256"] and
                metrics_hash == expected["metrics_sha256"])

    @staticmethod
    def _event(connection: sqlite3.Connection, run_id: str, kind: str,
               payload: Mapping[str, Any], at: str) -> None:
        connection.execute(
            "INSERT INTO events(run_id,at,kind,payload_json) VALUES (?,?,?,?)",
            (run_id, at, kind, _json(payload)),
        )

    @staticmethod
    def _status(connection: sqlite3.Connection, run_id: str) -> str:
        row = connection.execute(
            "SELECT status FROM backtest_runs WHERE run_id=?", (run_id,)
        ).fetchone()
        if row is None:
            raise RunStoreError(f"unknown run_id: {run_id}")
        return str(row["status"])

    def create_run(self, metadata: Mapping[str, Any]) -> str:
        if not isinstance(metadata, Mapping):
            raise RunStoreError("metadata must be a mapping")
        missing = _REQUIRED_METADATA - set(metadata)
        if missing:
            raise RunStoreError(f"metadata missing reproducibility fields: {', '.join(sorted(missing))}")
        encoded = _json(metadata)
        run_id = str(uuid.uuid4())
        now = _now()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                connection.execute(
                    "INSERT INTO backtest_runs(run_id,status,created_at,updated_at,metadata_json) "
                    "VALUES (?,?,?,?,?)",
                    (run_id, "queued", now, now, encoded),
                )
                self._event(connection, run_id, "created", {}, now)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise
        return run_id

    def start_run(self, run_id: str, pid: int) -> None:
        if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
            raise RunStoreError("pid must be a positive integer")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                row = connection.execute(
                    "SELECT status,pid FROM backtest_runs WHERE run_id=?", (run_id,)
                ).fetchone()
                if row is None:
                    raise RunStoreError(f"unknown run_id: {run_id}")
                status = str(row["status"])
                if status == "running" and row["pid"] == pid:
                    connection.execute("COMMIT")
                    return
                if status != "queued":
                    raise RunStoreError(f"cannot start run in status {status} or with a different PID")
                now = _now()
                connection.execute(
                    "UPDATE backtest_runs SET status='running', pid=?, started_at=?, updated_at=? "
                    "WHERE run_id=?", (pid, now, now, run_id),
                )
                self._event(connection, run_id, "started", {"pid": pid}, now)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def append_progress(self, run_id: str, snapshot: Mapping[str, Any]) -> None:
        if not isinstance(snapshot, Mapping):
            raise RunStoreError("progress snapshot must be a mapping")
        encoded = _json(snapshot)
        live_row: dict[str, Any] | None = None
        if "date" in snapshot and "equity" in snapshot:
            live_row = {
                key: snapshot[key] for key in (
                    "date", "equity", "cash", "gross_exposure", "drawdown",
                    "open_positions", "closed_trades",
                ) if key in snapshot
            }
            if "open_positions" in live_row:
                live_row["positions"] = live_row["open_positions"]
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                status = self._status(connection, run_id)
                if status not in {"running", "cancel_requested"}:
                    raise RunStoreError(f"cannot append progress in status {status}")
                now = _now()
                connection.execute(
                    "UPDATE backtest_runs SET progress_json=?, updated_at=? WHERE run_id=?",
                    (encoded, now, run_id),
                )
                if live_row is not None:
                    completed = snapshot.get("completed_sessions")
                    if isinstance(completed, bool) or not isinstance(completed, int) or completed < 1:
                        raise RunStoreError(
                            "equity progress requires positive integer completed_sessions"
                        )
                    connection.execute(
                        "INSERT INTO equity(run_id,seq,row_json) VALUES (?,?,?) "
                        "ON CONFLICT(run_id,seq) DO UPDATE SET row_json=excluded.row_json",
                        (run_id, completed - 1, _json(live_row, sort_keys=False)),
                    )
                self._event(connection, run_id, "progress", snapshot, now)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def finish_run(self, run_id: str, result: Any, metrics: Mapping[str, Any]) -> None:
        if not isinstance(metrics, Mapping):
            raise RunStoreError("metrics must be a mapping")
        result_fields = result if isinstance(result, Mapping) else vars(result)
        equity = _rows(result_fields.get("equity"), "equity")
        trades = _rows(result_fields.get("trades"), "trades")
        orders = _rows(result_fields.get("orders"), "orders")
        other_events = _rows(result_fields.get("events"), "events")
        summary = {
            key: value for key, value in result_fields.items()
            if key not in {"equity", "trades", "orders", "events"}
        }
        metrics_json = _json(metrics)
        summary_json = _json(summary)
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                status = self._status(connection, run_id)
                if status != "running":
                    raise RunStoreError(f"cannot finish run in status {status}")
                now = _now()
                # Replace provisional day-by-day progress with the complete,
                # authoritative engine curve in the same transaction.
                connection.execute("DELETE FROM equity WHERE run_id=?", (run_id,))
                connection.executemany(
                    "INSERT INTO equity(run_id,seq,row_json) VALUES (?,?,?)",
                    ((run_id, index, _json(row, sort_keys=False)) for index, row in enumerate(equity)),
                )
                connection.executemany(
                    "INSERT INTO trades(run_id,seq,row_json) VALUES (?,?,?)",
                    ((run_id, index, _json(row, sort_keys=False)) for index, row in enumerate(trades)),
                )
                for row in orders:
                    self._event(connection, run_id, "order", row, now)
                for row in other_events:
                    self._event(connection, run_id, "result_event", row, now)
                self._event(connection, run_id, "completed", {"equity_rows": len(equity),
                    "trade_rows": len(trades), "order_rows": len(orders)}, now)
                connection.execute(
                    "UPDATE backtest_runs SET status='completed', metrics_json=?, result_json=?, "
                    "finished_at=?, updated_at=? WHERE run_id=?",
                    (metrics_json, summary_json, now, now, run_id),
                )
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def _terminate(self, run_id: str, status: str, message: str | None) -> None:
        if status not in {"failed", "cancelled"}:
            raise RunStoreError(f"invalid terminal status: {status}")
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                previous = self._status(connection, run_id)
                if previous in _TERMINAL:
                    raise RunStoreError(f"cannot change terminal run in status {previous}")
                now = _now()
                connection.execute(
                    "UPDATE backtest_runs SET status=?, error_text=?, finished_at=?, updated_at=? "
                    "WHERE run_id=?", (status, message, now, now, run_id),
                )
                self._event(connection, run_id, status, {"message": message}, now)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    def fail_run(self, run_id: str, error: str) -> None:
        self._terminate(run_id, "failed", str(error))

    def cancel_run(self, run_id: str, reason: str | None = None) -> None:
        self._terminate(run_id, "cancelled", reason)

    def request_cancel(self, run_id: str) -> None:
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                status = self._status(connection, run_id)
                if status == "cancel_requested":
                    connection.execute("COMMIT")
                    return
                if status not in {"queued", "running"}:
                    raise RunStoreError(f"cannot request cancel in status {status}")
                now = _now()
                connection.execute(
                    "UPDATE backtest_runs SET status='cancel_requested', cancel_requested_at=?, "
                    "updated_at=? WHERE run_id=?", (now, now, run_id),
                )
                self._event(connection, run_id, "cancel_requested", {}, now)
                connection.execute("COMMIT")
            except Exception:
                connection.execute("ROLLBACK")
                raise

    @staticmethod
    def _run_dict(row: sqlite3.Row) -> dict[str, Any]:
        record = dict(row)
        for source, target in (
            ("metadata_json", "metadata"), ("progress_json", "progress"),
            ("metrics_json", "metrics"), ("result_json", "result"),
        ):
            value = record.pop(source)
            record[target] = json.loads(value) if value is not None else None
        progress = record["progress"] or {}
        record["worker_pid"] = record["pid"]
        record["cancel_requested"] = record["status"] == "cancel_requested"
        record["current_date"] = progress.get("date")
        record["positions"] = progress.get("open_positions")
        record["latest_signals"] = progress.get("latest_signals", [])
        return record

    def get_run(self, run_id: str) -> dict[str, Any]:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT * FROM backtest_runs WHERE run_id=?", (run_id,)
            ).fetchone()
            if row is None:
                raise RunStoreError(f"unknown run_id: {run_id}")
            return self._run_dict(row)

    def get_daily_snapshots(self, run_id: str, *, after_event_id: int = 0,
                            limit: int = 200) -> list[dict[str, Any]]:
        """Return stored trading-day frames for live playback and later inspection."""
        if isinstance(after_event_id, bool) or not isinstance(after_event_id, int) or after_event_id < 0:
            raise RunStoreError("after_event_id must be a non-negative integer")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
            raise RunStoreError("limit must be between 1 and 500")
        with self._connect() as connection:
            self._status(connection, run_id)
            rows = connection.execute(
                "SELECT event_id, payload_json FROM events "
                "WHERE run_id=? AND kind='progress' AND event_id>? "
                "ORDER BY event_id LIMIT ?", (run_id, after_event_id, limit),
            ).fetchall()
        return [{"event_id": row["event_id"], **json.loads(row["payload_json"])}
                for row in rows]

    def list_runs(self, *, limit: int = 100, status: str | None = None) -> list[dict[str, Any]]:
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10_000:
            raise RunStoreError("limit must be an integer from 1 to 10000")
        if status is not None and status not in _STATUSES:
            raise RunStoreError(f"unknown status: {status}")
        with self._connect() as connection:
            if status is None:
                rows = connection.execute(
                    "SELECT * FROM backtest_runs ORDER BY created_at DESC, run_id DESC LIMIT ?",
                    (limit,),
                ).fetchall()
            else:
                rows = connection.execute(
                    "SELECT * FROM backtest_runs WHERE status=? "
                    "ORDER BY created_at DESC, run_id DESC LIMIT ?", (status, limit),
                ).fetchall()
            return [self._run_dict(row) for row in rows]

    def has_active_strategy_runs(self, strategy_id: str) -> bool:
        """Check every unfinished Run, without the list_runs display limit."""
        with self._connect() as connection:
            rows = connection.execute(
                "SELECT metadata_json FROM backtest_runs "
                "WHERE status IN ('queued', 'running', 'cancel_requested')"
            ).fetchall()
            rows += connection.execute(
                "SELECT metadata_json FROM scanner_runs WHERE status IN ('queued','running')"
            ).fetchall()
        return any(json.loads(row["metadata_json"]).get("strategy_id") == strategy_id
                   for row in rows)

    def _get_rows(self, table: str, run_id: str) -> pd.DataFrame:
        # Only internal fixed table names reach this method.
        if table not in {"equity", "trades"}:
            raise AssertionError("invalid result table")
        with self._connect() as connection:
            self._status(connection, run_id)
            rows = connection.execute(
                f"SELECT row_json FROM {table} WHERE run_id=? ORDER BY seq", (run_id,)
            ).fetchall()
            return pd.DataFrame([json.loads(row["row_json"]) for row in rows])

    def get_equity(self, run_id: str) -> pd.DataFrame:
        return self._get_rows("equity", run_id)

    def get_trades(self, run_id: str) -> pd.DataFrame:
        return self._get_rows("trades", run_id)

    def get_events(self, run_id: str) -> pd.DataFrame:
        with self._connect() as connection:
            self._status(connection, run_id)
            rows = connection.execute(
                "SELECT event_id,at,kind,payload_json FROM events WHERE run_id=? ORDER BY event_id",
                (run_id,),
            ).fetchall()
            return pd.DataFrame(
                [{"event_id": row["event_id"], "at": row["at"],
                  "kind": row["kind"], "payload": json.loads(row["payload_json"])}
                 for row in rows],
                columns=["event_id", "at", "kind", "payload"],
            )

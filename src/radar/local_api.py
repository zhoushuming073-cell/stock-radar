"""Loopback API for the Stock Radar Web UI and published Sites frontend.

The database and credentials remain on this computer. Only an explicitly allowed
browser origin can read responses, and the server listens on 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
from collections import Counter
from functools import lru_cache
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event, Thread
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import duckdb
import yaml


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DB = DATA / "market.duckdb"
UNIVERSE = DATA / "universe.csv"
VALIDATION = DATA / "validation-summary.json"
SYMBOL = re.compile(r"^[A-Z0-9.\-]{1,20}$")
MAX_JSON_BYTES = 1_000_000
MAX_PLUGIN_BYTES = 5_000_000


@lru_cache(maxsize=1)
def lab_manager():
    from radar.lab.manager import RunManager
    return RunManager(ROOT)


def lab_runs() -> list[dict]:
    manager = lab_manager()
    manager.refresh()
    manager.launch_queued()
    manager.launch_queued_scanners()
    return manager.store.list_runs(limit=10_000)


def lab_strategies() -> list[dict]:
    from radar.lab.manager import _plain
    manager = lab_manager()
    registrations = manager.list_strategies()
    plugin_root = manager.plugin_dir.resolve()
    return [{
        "id": item.manifest.id,
        "version": item.manifest.version,
        "strategy_ref": f"{item.manifest.id}@{item.manifest.version}",
        "name": item.manifest.name,
        "description": item.manifest.description,
        "author": item.manifest.author.model_dump(),
        "tags": item.manifest.tags,
        "config": _plain(item.config),
        "removable": (not item.path.is_symlink()
                      and item.path.parent.resolve() == plugin_root
                      and item.path.name == f"{item.manifest.id}@{item.manifest.version}"),
    } for item in registrations]


def lab_parameter_schema(strategy_id: str) -> list[dict]:
    from radar.backtest.runner import load_backtest_config
    from radar.lab.parameters import execution_defaults_from_legacy
    from radar.lab.scanner import evaluation_settings
    from radar.lab.schema import parameter_schema
    manager = lab_manager()
    try:
        if "@" in strategy_id:
            identifier, version = strategy_id.rsplit("@", 1)
            match = manager.registry.get(identifier, version)
        else:
            match = manager.registry.get(strategy_id)
    except KeyError as error:
        raise ValueError(f"unknown strategy: {strategy_id}") from error
    execution = execution_defaults_from_legacy(
        load_backtest_config(ROOT / "config" / "backtest.yaml"),
        slippage_bps=10, execution_timing="next_open")
    return parameter_schema(match.manifest.id, match.config,
                            evaluation_settings(None), execution)


def lab_split_status() -> dict:
    from radar.backtest.runner import split_dates

    windows = split_dates(DATA / "phase2-research.duckdb", ROOT / "config/research.yaml")
    return {name: {"signal_start": str(window[0].date()),
                   "signal_end": str(window[1].date()),
                   "evaluation_end": str(window[2].date())}
            for name, window in windows.items()
            if name in {"train", "validation", "test", "fresh_oos"}}


def lab_universe_status() -> dict:
    from radar.lab.universe import current_snapshot_provenance, LocalSecurityMaster
    base = {"current": current_snapshot_provenance().metadata(),
            "point_in_time_available": False}
    csv_path = DATA / "security-master.csv"
    manifest_path = DATA / "security-master-manifest.json"
    if csv_path.exists() and manifest_path.exists():
        try:
            base["point_in_time"] = LocalSecurityMaster(csv_path, manifest_path).provenance().metadata()
            base["point_in_time_available"] = True
        except ValueError as error:
            base["point_in_time_error"] = str(error)
    return base


def lab_pit_readiness(split: str) -> dict:
    from radar.backtest.runner import split_dates
    from radar.lab.readiness import local_readiness
    if split not in {"train", "validation", "test"}:
        raise ValueError("PIT readiness split must be train, validation or test")
    dates = split_dates(DATA / "phase2-research.duckdb", ROOT / "config/research.yaml")
    start, _, end = dates[split]
    sessions = [day for day in dates["sessions"] if start <= day <= end]
    report = local_readiness(ROOT, "point_in_time", sessions)
    report["split"] = split
    report["requested_coverage"] = {"start": str(start.date()), "end": str(end.date())}
    store = lab_manager().store
    runs = store.list_scanner_runs(limit=1000)
    relevant = [run for run in runs if run["status"] == "completed" and
                run["metadata"].get("split") == split and
                run["metadata"].get("universe_mode") == "point_in_time"]
    reasons = store.scanner_censor_reasons([run["run_id"] for run in relevant])
    report["scanner_censoring_audit"] = {
        "completed_pit_runs": len(relevant),
        "censored_candidates": sum(int((run.get("metrics") or {}).get("censored_candidate_count") or 0)
                                   for run in relevant),
        "censored_background": sum(int((run.get("metrics") or {}).get("censored_background_count") or 0)
                                  for run in relevant),
        "candidate_reasons": reasons,
        "terminal_outcome_censored": reasons.get("terminal_event_without_valued_outcome", 0),
        "missing_outcome_censored": sum(count for reason, count in reasons.items()
                                        if reason in {"missing_symbol_bar", "missing_price_data",
                                                      "security_no_longer_eligible", "insufficient_future_sessions"}),
    }
    return report


def lab_spy(start: str, end: str) -> list[dict]:
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", start) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", end):
        raise ValueError("dates must use YYYY-MM-DD")
    with duckdb.connect(str(DATA / "phase2-research.duckdb"), read_only=True) as connection:
        rows = connection.execute(
            "SELECT date, close FROM daily_bars WHERE symbol='SPY' "
            "AND date BETWEEN ? AND ? ORDER BY date", [start, end],
        ).fetchall()
    return [{"date": date.isoformat(), "close": close} for date, close in rows]


def overview() -> dict[str, object]:
    with duckdb.connect(str(DB), read_only=True) as connection:
        bars, symbols, first, last = connection.execute(
            "SELECT COUNT(*), COUNT(DISTINCT symbol), MIN(date), MAX(date) FROM daily_bars"
        ).fetchone()
    with UNIVERSE.open(encoding="utf-8-sig", newline="") as stream:
        universe = list(csv.DictReader(stream))
    with VALIDATION.open(encoding="utf-8") as stream:
        report = json.load(stream)
    issues = report.get("issues", [])
    counts = Counter(issue.get("code") for issue in issues)
    return {
        "bars": bars,
        "symbols_with_bars": symbols,
        "first": first.isoformat() if first else None,
        "last": last.isoformat() if last else None,
        "universe": [{"symbol": row["symbol"], "name": row["name"]} for row in universe],
        "errors": sum(issue.get("severity") == "error" for issue in issues),
        "warnings": sum(issue.get("severity") == "warning" for issue in issues),
        "warning_counts": counts,
        "issues": [
            {
                "symbol": issue.get("symbol"),
                "date": issue.get("date"),
                "code": issue.get("code"),
                "message": issue.get("message"),
            }
            for issue in issues
        ],
        "report_stale": VALIDATION.stat().st_mtime_ns < DB.stat().st_mtime_ns,
        "report_updated": VALIDATION.stat().st_mtime,
    }


def data_status() -> dict[str, object]:
    """Read the former data/settings panels without exposing credentials."""
    status_path = DATA / "daily-update-status.json"
    try:
        raw_status = json.loads(status_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        raw_status = {}
    if not isinstance(raw_status, dict):
        raw_status = {}
    sync = {key: raw_status.get(key) for key in ("state", "target_date", "finished_at", "error")}
    with duckdb.connect(str(DB), read_only=True) as connection:
        rows = connection.execute("""
            SELECT a.exchange, COUNT(*) AS total, COUNT(b.symbol) AS daily,
                   MAX(b.last_date) AS last_update
            FROM assets a
            LEFT JOIN (SELECT symbol, MAX(date) AS last_date FROM daily_bars GROUP BY symbol) b
              ON a.symbol=b.symbol
            WHERE a.status='active' AND a.tradable
            GROUP BY a.exchange ORDER BY total DESC
        """).fetchall()
    coverage = [{"exchange": exchange, "total": total, "daily": daily,
                 "last_update": str(last_update) if last_update else None}
                for exchange, total, daily, last_update in rows]
    try:
        backtest = yaml.safe_load((ROOT / "config" / "backtest.yaml").read_text(encoding="utf-8")) or {}
        research = yaml.safe_load((ROOT / "config" / "research.yaml").read_text(encoding="utf-8")) or {}
    except (OSError, yaml.YAMLError):
        backtest, research = {}, {}
    costs = research.get("illustrative_costs", {}) if isinstance(research, dict) else {}
    return {"sync": sync, "coverage": coverage, "settings": {
        "provider": "Alpaca",
        "backtest": {key: backtest.get(key) for key in (
            "initial_capital", "max_new_candidates", "take_profit", "stop_loss",
            "max_holding_sessions", "max_position_fraction", "base_slippage_bps")},
        "illustrative_costs": {key: costs.get(key) for key in (
            "profile", "commission_per_share", "platform_per_share")},
    }}


def start_daily_sync() -> None:
    """Trigger the existing quiet Windows task; it owns update concurrency."""
    if os.name != "nt":
        raise OSError("local background sync is configured only on Windows")
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-Command",
         "Start-ScheduledTask -TaskName 'StockRadar-DailyUpdate'"],
        capture_output=True, text=True, timeout=15, check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    if result.returncode:
        raise OSError(result.stderr.strip() or "daily update task could not start")


def symbol_data(symbol: str) -> dict[str, object]:
    if not SYMBOL.fullmatch(symbol):
        raise ValueError("invalid symbol")
    with duckdb.connect(str(DB), read_only=True) as connection:
        asset_result = connection.execute(
            "SELECT name, exchange, asset_class, status FROM assets WHERE symbol = ?", [symbol]
        ).fetchone()
        rows = connection.execute(
            "SELECT date, open, high, low, close, volume FROM daily_bars "
            "WHERE symbol = ? ORDER BY date", [symbol]
        ).fetchall()
    return {
        "symbol": symbol,
        "asset": dict(zip(("name", "exchange", "asset_class", "status"), asset_result))
        if asset_result else None,
        "bars": [
            {"date": row[0].isoformat(), "open": row[1], "high": row[2],
             "low": row[3], "close": row[4], "volume": row[5]}
            for row in rows
        ],
    }


def make_handler(allowed_origins: set[str]):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:
            # pythonw.exe has no stderr; keep the background task silent.
            return

        def _allowed(self) -> bool:
            origin = self.headers.get("Origin")
            return origin is None or origin in allowed_origins

        def _write_allowed(self) -> bool:
            return self.headers.get("Origin") in allowed_origins

        def _headers(self, status: int, content_type: str = "application/json; charset=utf-8") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            origin = self.headers.get("Origin")
            if origin in allowed_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Content-Type")
                if self.headers.get("Access-Control-Request-Private-Network") == "true":
                    self.send_header("Access-Control-Allow-Private-Network", "true")
            self.end_headers()

        def _json(self, status: int, payload: object) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self._headers(status)
            self.wfile.write(body)

        def do_OPTIONS(self) -> None:
            if not self._allowed():
                self._json(HTTPStatus.FORBIDDEN, {"error": "origin is not allowed"})
            else:
                self._headers(HTTPStatus.NO_CONTENT)

        def do_GET(self) -> None:
            if not self._allowed():
                self._json(HTTPStatus.FORBIDDEN, {"error": "origin is not allowed"})
                return
            target = urlsplit(self.path)
            try:
                if target.path == "/health":
                    payload = {"ok": True, "service": "stock-radar-api", "database_present": DB.is_file()}
                elif target.path == "/api/overview":
                    payload = overview()
                elif target.path == "/api/data/status":
                    payload = data_status()
                elif target.path == "/api/symbol":
                    symbol = parse_qs(target.query).get("symbol", [""])[0].upper()
                    payload = symbol_data(symbol)
                elif target.path == "/api/lab/strategies":
                    payload = lab_strategies()
                elif target.path == "/api/lab/parameter-schema":
                    strategy_id = parse_qs(target.query).get("strategy_id", [""])[0]
                    payload = lab_parameter_schema(strategy_id)
                elif target.path == "/api/lab/splits":
                    payload = lab_split_status()
                elif target.path == "/api/lab/universe-status":
                    payload = lab_universe_status()
                elif target.path == "/api/lab/pit-readiness":
                    payload = lab_pit_readiness(parse_qs(target.query).get("split", ["validation"])[0])
                elif target.path == "/api/lab/runs":
                    payload = lab_runs()
                elif target.path == "/api/lab/scanner/runs":
                    manager = lab_manager()
                    manager.launch_queued_scanners()
                    payload = manager.store.list_scanner_runs(limit=1000)
                elif target.path in {"/api/lab/scanner/run", "/api/lab/scanner/candidates"}:
                    run_id = parse_qs(target.query).get("id", [""])[0]
                    if not re.fullmatch(r"[0-9a-f-]{36}", run_id):
                        raise ValueError("invalid scanner run ID")
                    store = lab_manager().store
                    payload = (store.get_scanner_run(run_id) if target.path.endswith("/run")
                               else store.get_scanner_candidates(
                                   run_id, max_rank=int(parse_qs(target.query).get("top", ["20"])[0]),
                                   limit=100000))
                elif target.path == "/api/lab/experiments":
                    from radar.lab.experiments import summarize_experiments
                    payload = summarize_experiments(
                        lab_runs(), lab_manager().store.list_scanner_runs(limit=1000))
                elif target.path == "/api/lab/exports":
                    from radar.lab.research_export import list_research_bundles
                    payload = list_research_bundles(DATA / "research-exports")
                elif target.path == "/api/lab/export/download":
                    bundle_id = parse_qs(target.query).get("id", [""])[0]
                    if not re.fullmatch(r"[0-9a-f-]{36}", bundle_id):
                        raise ValueError("invalid bundle ID")
                    path = DATA / "research-exports" / f"research-{bundle_id}.zip"
                    if not path.is_file():
                        self._json(HTTPStatus.NOT_FOUND, {"error": "bundle not found"})
                        return
                    self.send_response(HTTPStatus.OK)
                    self.send_header("Content-Type", "application/zip")
                    self.send_header("Content-Disposition", f'attachment; filename="{path.name}"')
                    self.send_header("Content-Length", str(path.stat().st_size))
                    self.send_header("Cache-Control", "no-store")
                    origin = self.headers.get("Origin")
                    if origin in allowed_origins:
                        self.send_header("Access-Control-Allow-Origin", origin)
                        self.send_header("Vary", "Origin")
                    self.end_headers()
                    with path.open("rb") as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                            self.wfile.write(chunk)
                    return
                elif target.path in {"/api/lab/run", "/api/lab/equity", "/api/lab/trades",
                                     "/api/lab/events", "/api/lab/days"}:
                    run_id = parse_qs(target.query).get("id", [""])[0]
                    if not re.fullmatch(r"[0-9a-f-]{36}", run_id):
                        raise ValueError("invalid run ID")
                    store = lab_manager().store
                    if target.path.endswith("/run"):
                        payload = store.get_run(run_id)
                    elif target.path.endswith("/equity"):
                        payload = store.get_equity(run_id).to_dict("records")
                    elif target.path.endswith("/trades"):
                        payload = store.get_trades(run_id).tail(100).to_dict("records")
                    elif target.path.endswith("/days"):
                        after = int(parse_qs(target.query).get("after", ["0"])[0])
                        payload = store.get_daily_snapshots(run_id, after_event_id=after)
                    else:
                        payload = store.get_events(run_id).tail(100).to_dict("records")
                elif target.path == "/api/lab/spy":
                    query = parse_qs(target.query)
                    payload = lab_spy(query.get("start", [""])[0], query.get("end", [""])[0])
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
            except (ValueError, KeyError) as error:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            except (OSError, duckdb.Error, json.JSONDecodeError) as error:
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(error)})
                return
            self._json(HTTPStatus.OK, payload)

        def do_POST(self) -> None:
            if not self._write_allowed():
                self._json(HTTPStatus.FORBIDDEN, {"error": "origin is not allowed for writes"})
                return
            target = urlsplit(self.path).path
            if target not in {"/api/data/sync", "/api/lab/import", "/api/lab/run", "/api/lab/timeline", "/api/lab/cancel",
                              "/api/lab/uninstall", "/api/lab/run/rename", "/api/lab/run/archive", "/api/lab/run/restore",
                              "/api/lab/experiment", "/api/lab/scanner/run", "/api/lab/export"}:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                maximum = MAX_PLUGIN_BYTES if target.endswith("/import") else MAX_JSON_BYTES
                if not 0 < length <= maximum:
                    raise ValueError("invalid request size")
                body = self.rfile.read(length)
                if target == "/api/data/sync":
                    if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                        raise ValueError("request must be JSON")
                    if not isinstance(json.loads(body), dict):
                        raise ValueError("request must be an object")
                    start_daily_sync()
                    payload = {"ok": True}
                elif target.endswith("/import"):
                    manager = lab_manager()
                    if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/zip":
                        raise ValueError("strategy upload must be a ZIP")
                    with TemporaryDirectory(prefix="stock-radar-upload-") as directory:
                        path = Path(directory) / "strategy.zip"
                        path.write_bytes(body)
                        registration = manager.import_zip(path)
                    payload = {"id": registration.manifest.id,
                               "version": registration.manifest.version,
                               "name": registration.manifest.name}
                else:
                    manager = lab_manager()
                    if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                        raise ValueError("request must be JSON")
                    data = json.loads(body)
                    if not isinstance(data, dict):
                        raise ValueError("request must be an object")
                    if target == "/api/lab/export":
                        from radar.lab.research_export import build_research_bundle
                        payload = build_research_bundle(
                            manager.store, data.get("run_ids"),
                            DATA / "research-exports", name=data.get("name", "Research export"))
                    elif target in {"/api/lab/run/rename", "/api/lab/run/archive", "/api/lab/run/restore"}:
                        run_id = data.get("run_id")
                        if not isinstance(run_id, str) or not re.fullmatch(r"[0-9a-f-]{36}", run_id):
                            raise ValueError("invalid run ID")
                        if target.endswith("/rename"):
                            payload = manager.store.rename_run(run_id, data.get("name"))
                        else:
                            payload = manager.store.set_run_archived(run_id, target.endswith("/archive"))
                    elif target.endswith("/experiment"):
                        from radar.lab.experiments import queue_experiment
                        payload = queue_experiment(
                            manager, kind=str(data["kind"]),
                            strategy_id=str(data["strategy_id"]),
                            split=str(data.get("split", "validation")),
                            grid=data.get("grid"),
                            slippage_bps=float(data.get("slippage_bps", 10)),
                            run_type=str(data.get("run_type", "backtest")),
                            config_override=data.get("config"),
                            evaluation_overrides=data.get("evaluation"),
                            execution_overrides=data.get("execution"),
                            universe_mode=str(data.get("universe_mode", "current_snapshot")),
                        )
                    elif target == "/api/lab/scanner/run":
                        strategy_id = data.get("strategy_id")
                        if not isinstance(strategy_id, str) or not strategy_id:
                            raise ValueError("strategy_id must be a non-empty string")
                        config = data.get("config")
                        if config is not None and not isinstance(config, dict):
                            raise ValueError("config must be an object")
                        evaluation = data.get("evaluation")
                        if evaluation is not None and not isinstance(evaluation, dict):
                            raise ValueError("evaluation must be an object")
                        legacy_cap = ({"max_candidates": data["max_candidates"]}
                                      if "max_candidates" in data else {})
                        run_id = manager.queue_scanner(
                            strategy_id, split=str(data.get("split", "validation")),
                            config_override=config, evaluation_overrides=evaluation,
                            universe_mode=str(data.get("universe_mode", "current_snapshot")),
                            **legacy_cap)
                        manager.launch_queued_scanners()
                        payload = {"run_id": run_id}
                    elif target.endswith("/cancel"):
                        manager.cancel(str(data["run_id"]), str(data.get("run_type", "backtest")))
                        payload = {"ok": True}
                    elif target.endswith("/uninstall"):
                        strategy_id = data.get("strategy_id")
                        if not isinstance(strategy_id, str) or not strategy_id:
                            raise ValueError("strategy_id must be a non-empty string")
                        removed = manager.uninstall_strategy(strategy_id)
                        payload = {"ok": True, "removed_versions": removed}
                    elif target.endswith("/timeline"):
                        strategy_id = data.get("strategy_id")
                        config = data.get("config")
                        pace_ms = data.get("pace_ms", 500)
                        if not isinstance(strategy_id, str) or not isinstance(config, dict):
                            raise ValueError("timeline needs a strategy_id and configuration")
                        batch_id = str(uuid4())
                        assigned_ids = [str(uuid4()) for _ in range(3)]
                        requests = [{
                            "strategy_ids": [strategy_id], "split": stage,
                            "slippage_bps": float(data.get("slippage_bps", 10)),
                            "configs_by_strategy": {strategy_id: config},
                            "batch_id": batch_id,
                            "after_run_id": assigned_ids[index - 1] if index else None,
                            "assigned_ids": [assigned_ids[index]],
                            "pace_ms": pace_ms,
                            "execution_overrides": data.get("execution"),
                            "universe_mode": str(data.get("universe_mode", "current_snapshot")),
                            "source_scanner_run_id": data.get("source_scanner_run_id"),
                        } for index, stage in enumerate(("train", "validation", "test"))]
                        run_ids = manager.queue_run_requests(requests)
                        manager.launch_queued()
                        payload = {"batch_id": batch_id, "run_ids": run_ids}
                    else:
                        strategy_runs = data.get("strategy_runs")
                        if strategy_runs is not None:
                            if not isinstance(strategy_runs, list) or not strategy_runs or len(strategy_runs) > 64:
                                raise ValueError("strategy_runs must contain 1 to 64 items")
                            requests = []
                            for item in strategy_runs:
                                if (not isinstance(item, dict) or
                                        not isinstance(item.get("strategy_ref"), str) or
                                        not isinstance(item.get("config"), dict) or
                                        not isinstance(item.get("execution", {}), dict)):
                                    raise ValueError("invalid strategy run settings")
                                reference = item["strategy_ref"]
                                if "@" not in reference or not all(reference.rsplit("@", 1)):
                                    raise ValueError("strategy_ref must include an exact version")
                                requests.append({
                                    "strategy_ids": [reference],
                                    "split": str(data.get("split", "validation")),
                                    "slippage_bps": float(item.get("slippage_bps", 10)),
                                    "configs_by_strategy": {reference: item["config"]},
                                    "execution_overrides": item.get("execution", {}),
                                    "universe_mode": str(data.get("universe_mode", "current_snapshot")),
                                    "source_scanner_run_id": data.get("source_scanner_run_id"),
                                })
                            run_ids = manager.queue_run_requests(requests)
                        else:
                            ids = data.get("strategy_ids")
                            if not isinstance(ids, list) or not all(isinstance(item, str) for item in ids):
                                raise ValueError("strategy_ids must be a list")
                            configs = data.get("configs_by_strategy")
                            if configs is not None and not isinstance(configs, dict):
                                raise ValueError("configs_by_strategy must be an object")
                            run_ids = manager.queue_runs(
                                ids, split=str(data.get("split", "validation")),
                                slippage_bps=float(data.get("slippage_bps", 10)),
                                configs_by_strategy=configs,
                                execution_overrides=data.get("execution"),
                                universe_mode=str(data.get("universe_mode", "current_snapshot")),
                                source_scanner_run_id=data.get("source_scanner_run_id"),
                            )
                        manager.launch_queued()
                        payload = {"run_ids": run_ids}
            except (ValueError, KeyError, TypeError, json.JSONDecodeError) as error:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            except Exception as error:
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(error)})
                return
            self._json(HTTPStatus.OK, payload)

    return Handler


def start_lab_dispatcher(interval_seconds: float = 5.0) -> Event:
    """Keep queued Runs moving even after every browser tab is closed."""
    stop = Event()

    def dispatch() -> None:
        while not stop.wait(interval_seconds):
            try:
                lab_manager().launch_queued()
                lab_manager().launch_queued_scanners()
            except Exception as error:
                log = DATA / "strategy-lab" / "dispatcher.log"
                log.parent.mkdir(parents=True, exist_ok=True)
                with log.open("a", encoding="utf-8") as stream:
                    stream.write(f"{type(error).__name__}: {error}\n")

    Thread(target=dispatch, name="stock-radar-lab-dispatcher", daemon=True).start()
    return stop


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock Radar loopback API")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-origin", action="append", default=[])
    args = parser.parse_args()
    for origin in args.allow_origin:
        if not origin.startswith(("https://", "http://127.0.0.1:")):
            parser.error("allowed origins must be HTTPS or local development origins")
    allowed_origins = set(args.allow_origin)
    allowed_origins.add("http://127.0.0.1:4174")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(allowed_origins))
    dispatcher_stop = start_lab_dispatcher()
    import sys
    if sys.stdout is not None:
        print(f"Stock Radar local API on http://127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    finally:
        dispatcher_stop.set()


if __name__ == "__main__":
    main()

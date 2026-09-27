"""Loopback API for the private Sites dashboard and local Strategy Lab.

The database and credentials remain on this computer. Only an explicitly allowed
browser origin can read responses, and the server listens on 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
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
    removable: dict[str, bool] = {}
    for item in registrations:
        imported = (not item.path.is_symlink()
                    and item.path.parent.resolve() == plugin_root
                    and item.path.name == f"{item.manifest.id}@{item.manifest.version}")
        removable[item.manifest.id] = removable.get(item.manifest.id, True) and imported
    return [{
        "id": item.manifest.id,
        "version": item.manifest.version,
        "name": item.manifest.name,
        "description": item.manifest.description,
        "author": item.manifest.author.model_dump(),
        "tags": item.manifest.tags,
        "config": _plain(item.config),
        "removable": removable[item.manifest.id],
    } for item in registrations]


def lab_parameter_schema(strategy_id: str) -> list[dict]:
    from radar.backtest.runner import load_backtest_config
    from radar.lab.parameters import execution_defaults_from_legacy
    from radar.lab.scanner import evaluation_settings
    from radar.lab.schema import parameter_schema
    manager = lab_manager()
    match = next((item for item in manager.list_strategies()
                  if item.manifest.id == strategy_id), None)
    if match is None:
        raise ValueError(f"unknown strategy: {strategy_id}")
    execution = execution_defaults_from_legacy(
        load_backtest_config(ROOT / "config" / "backtest.yaml"),
        slippage_bps=10, execution_timing="next_open")
    return parameter_schema(strategy_id, match.config,
                            evaluation_settings(None), execution)


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
                    payload = {"ok": True, "database_present": DB.is_file()}
                elif target.path == "/api/overview":
                    payload = overview()
                elif target.path == "/api/symbol":
                    symbol = parse_qs(target.query).get("symbol", [""])[0].upper()
                    payload = symbol_data(symbol)
                elif target.path == "/api/lab/strategies":
                    payload = lab_strategies()
                elif target.path == "/api/lab/parameter-schema":
                    strategy_id = parse_qs(target.query).get("strategy_id", [""])[0]
                    payload = lab_parameter_schema(strategy_id)
                elif target.path == "/api/lab/universe-status":
                    payload = lab_universe_status()
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
                    payload = summarize_experiments(lab_runs())
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
            if target not in {"/api/lab/import", "/api/lab/run", "/api/lab/timeline", "/api/lab/cancel",
                              "/api/lab/uninstall",
                              "/api/lab/experiment", "/api/lab/scanner/run"}:
                self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                maximum = MAX_PLUGIN_BYTES if target.endswith("/import") else MAX_JSON_BYTES
                if not 0 < length <= maximum:
                    raise ValueError("invalid request size")
                body = self.rfile.read(length)
                manager = lab_manager()
                if target.endswith("/import"):
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
                    if self.headers.get("Content-Type", "").split(";", 1)[0] != "application/json":
                        raise ValueError("request must be JSON")
                    data = json.loads(body)
                    if not isinstance(data, dict):
                        raise ValueError("request must be an object")
                    if target.endswith("/experiment"):
                        from radar.lab.experiments import queue_experiment
                        payload = queue_experiment(
                            manager, kind=str(data["kind"]),
                            strategy_id=str(data["strategy_id"]),
                            split=str(data.get("split", "validation")),
                            grid=data.get("grid"),
                            slippage_bps=float(data.get("slippage_bps", 10)),
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
                        manager.cancel(str(data["run_id"]))
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
                        run_ids = []
                        predecessor = None
                        for stage in ("train", "validation", "test"):
                            run_id = manager.queue_runs(
                                [strategy_id], split=stage,
                                slippage_bps=float(data.get("slippage_bps", 10)),
                                configs_by_strategy={strategy_id: config},
                                batch_id=batch_id, after_run_id=predecessor,
                                pace_ms=pace_ms,
                                execution_overrides=data.get("execution"),
                                universe_mode=str(data.get("universe_mode", "current_snapshot")),
                                source_scanner_run_id=data.get("source_scanner_run_id"),
                            )[0]
                            run_ids.append(run_id)
                            predecessor = run_id
                        manager.launch_queued()
                        payload = {"batch_id": batch_id, "run_ids": run_ids}
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
        if not origin.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
            parser.error("allowed origins must be HTTPS or local development origins")
    allowed_origins = set(args.allow_origin)
    allowed_origins.add("http://127.0.0.1:4174")
    allowed_origins.add("http://localhost:4174")
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

"""Read-only loopback API for the private Sites dashboard.

The database and credentials remain on this computer. Only an explicitly allowed
browser origin can read responses, and the server listens on 127.0.0.1 only.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
from collections import Counter
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import duckdb


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DB = DATA / "market.duckdb"
UNIVERSE = DATA / "universe.csv"
VALIDATION = DATA / "validation-summary.json"
SYMBOL = re.compile(r"^[A-Z0-9.\-]{1,20}$")


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

        def _headers(self, status: int, content_type: str = "application/json; charset=utf-8") -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            origin = self.headers.get("Origin")
            if origin in allowed_origins:
                self.send_header("Access-Control-Allow-Origin", origin)
                self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
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
                else:
                    self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
                    return
            except ValueError as error:
                self._json(HTTPStatus.BAD_REQUEST, {"error": str(error)})
                return
            except (OSError, duckdb.Error, json.JSONDecodeError) as error:
                self._json(HTTPStatus.SERVICE_UNAVAILABLE, {"error": str(error)})
                return
            self._json(HTTPStatus.OK, payload)

    return Handler


def main() -> None:
    parser = argparse.ArgumentParser(description="Stock Radar loopback read-only API")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--allow-origin", action="append", required=True)
    args = parser.parse_args()
    for origin in args.allow_origin:
        if not origin.startswith(("https://", "http://127.0.0.1:", "http://localhost:")):
            parser.error("allowed origins must be HTTPS or local development origins")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(set(args.allow_origin)))
    import sys
    if sys.stdout is not None:
        print(f"Stock Radar local API on http://127.0.0.1:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

"""Unattended local daily update: Alpaca -> DuckDB -> validation report."""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import dotenv_values

from radar.app import run_sync, run_validation
from radar.config import load_credentials, load_settings
from radar.providers.alpaca import AlpacaProvider


ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "data" / "daily-update-status.json"


def target_date(now: datetime) -> str:
    """Latest safely completed US market date, including daylight time changes."""
    ny = now.astimezone(ZoneInfo("America/New_York"))
    day = ny.date() if ny.hour >= 18 else ny.date() - timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day.isoformat()


def credentials(root: Path) -> tuple[str, str]:
    """Resolve Alpaca credentials from .env or the existing user-owned key file."""
    try:
        return load_credentials(root)
    except ValueError:
        # Existing user-owned credential file, kept outside the project and Site.
        fallback = root.parent / "alpacakey.txt"
        if not fallback.is_file():
            raise ValueError("Alpaca credentials missing: set .env or provide alpacakey.txt beside the project") from None
        values = dotenv_values(fallback)
        key, secret = values.get("ALPACA_API_KEY"), values.get("ALPACA_SECRET_KEY")
        if not key or not secret:
            raise ValueError("alpacakey.txt needs ALPACA_API_KEY and ALPACA_SECRET_KEY") from None
        return key, secret


def write_status(payload: dict[str, object]) -> None:
    STATUS.parent.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=STATUS.parent, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
        os.replace(temporary, STATUS)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Update local US daily bars and validation")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--if-due", action="store_true", help="skip a successfully completed target date")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    end = target_date(now)
    key, secret = credentials(ROOT)
    if args.dry_run:
        if sys.stdout is not None:
            print(json.dumps({"credentials_found": bool(key and secret), "target_date": end,
                              "database": str(load_settings(ROOT).database_path)}, ensure_ascii=False))
        return 0
    if args.if_due and STATUS.is_file():
        try:
            previous = json.loads(STATUS.read_text(encoding="utf-8"))
            if previous.get("state") == "succeeded" and previous.get("target_date", "") >= end:
                return 0
        except (OSError, ValueError):
            pass
    status: dict[str, object] = {"started_at": now.isoformat(), "target_date": end, "state": "running"}
    write_status(status)
    try:
        settings = load_settings(ROOT)
        provider = AlpacaProvider.from_credentials(key, secret)
        from datetime import date

        sync = run_sync(settings, provider, end=date.fromisoformat(end))
        status["sync"] = {key: value for key, value in sync.items() if key != "failed_symbols"}
        status["failed_symbol_count"] = len(sync["failed_symbols"])
        validation = run_validation(settings, provider, end=date.fromisoformat(end))
        status["validation"] = validation
        status["state"] = "succeeded" if not sync["failed_symbols"] and validation["errors"] == 0 else "attention"
        return 0 if status["state"] == "succeeded" else 2
    except Exception as error:
        status["state"] = "failed"
        status["error"] = str(error)
        raise
    finally:
        status["finished_at"] = datetime.now(timezone.utc).isoformat()
        write_status(status)
        if sys.stdout is not None:
            print(json.dumps(status, ensure_ascii=False))


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as error:
        if sys.stderr is not None:
            print(f"Daily update failed: {error}", file=sys.stderr)
        sys.exit(1)

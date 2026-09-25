"""Phase 1 command-line orchestration; no trading endpoints are used."""

from __future__ import annotations

import argparse
import json
import logging
import os
import tempfile
from datetime import date, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from radar.config import Settings, load_credentials, load_settings
from radar.db import get_connection, upsert_assets
from radar.export.csv_exporter import export_universe_csv
from radar.ingestion.bars import ingest_daily_bars
from radar.providers.alpaca import AlpacaProvider
from radar.universe.filters import filter_eligible_assets
from radar.models import AssetRecord
from radar.validation.bars import validate_database


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, ensure_ascii=False)
        os.replace(temporary, path)
    except BaseException:
        if os.path.exists(temporary):
            os.unlink(temporary)
        raise


def _target_sessions(provider: AlpacaProvider, end: date, count: int) -> list[date]:
    if count < 1:
        raise ValueError("lookback must be positive")
    calendar_start = end - timedelta(days=max(30, count * 2))
    sessions = provider.get_market_sessions(calendar_start, end)
    if len(sessions) < count:
        raise ValueError(f"calendar returned only {len(sessions)} sessions; need {count}")
    return sessions[-count:]


def run_sync(
    settings: Settings,
    provider: AlpacaProvider,
    *,
    end: date,
    lookback: int | None = None,
    max_symbols: int | None = None,
) -> dict[str, object]:
    """Refresh master/universe, then fill only absent daily-bar sessions."""
    count = lookback or settings.lookback_sessions
    if count < 1 or (max_symbols is not None and max_symbols < 1):
        raise ValueError("lookback and max_symbols must be positive")
    connection = get_connection(settings.database_path)
    try:
        assets = provider.get_assets()
        asset_stats = upsert_assets(connection, assets)
        eligible = filter_eligible_assets(assets)
        export_universe_csv(eligible, settings.project_root / "data" / "universe.csv")
        selected = eligible[:max_symbols] if max_symbols else eligible
        target_sessions = _target_sessions(provider, end, count)
        bars = ingest_daily_bars(
            connection,
            provider,
            [asset.symbol for asset in selected],
            target_sessions,
            feed=settings.feed,
            adjustment=settings.adjustment,
        )
        issue_report = settings.project_root / "data" / "ingestion-issues.json"
        _atomic_json(
            issue_report,
            {
                "failed_symbols": bars.failed_symbols,
                "issues": [issue.model_dump(mode="json") for issue in bars.issues],
            },
        )
        return {
            "assets_received": len(assets),
            "assets_inserted": asset_stats.inserted,
            "assets_updated": asset_stats.updated,
            "eligible_symbols": len(eligible),
            "symbols_ingested": len(selected),
            "session_start": target_sessions[0].isoformat(),
            "session_end": target_sessions[-1].isoformat(),
            "bars_fetched": bars.fetched_rows,
            "bars_inserted": bars.inserted_rows,
            "bars_updated": bars.updated_rows,
            "bars_rejected": bars.rejected_rows,
            "provider_batches": bars.batch_count,
            "failed_symbols": bars.failed_symbols,
            "validation_issue_count": len(bars.issues),
            "issue_report_path": str(issue_report),
        }
    finally:
        connection.close()


def run_validation(
    settings: Settings,
    provider: AlpacaProvider,
    *,
    end: date,
    lookback: int | None = None,
    max_symbols: int | None = None,
) -> dict[str, object]:
    if not settings.database_path.is_file():
        raise FileNotFoundError(f"database does not exist: {settings.database_path}")
    count = lookback or settings.lookback_sessions
    if max_symbols is not None and max_symbols < 1:
        raise ValueError("max_symbols must be positive")
    sessions = _target_sessions(provider, end, count)
    import duckdb

    connection = duckdb.connect(str(settings.database_path), read_only=True)
    try:
        result = connection.execute(
            """
            SELECT * FROM assets
            WHERE last_seen = (SELECT MAX(last_seen) FROM assets)
            """
        )
        names = [field[0] for field in result.description]
        assets = [AssetRecord(**dict(zip(names, row))) for row in result.fetchall()]
        eligible = filter_eligible_assets(assets)
        selected = eligible[:max_symbols] if max_symbols else eligible
        summary = validate_database(
            connection, [asset.symbol for asset in selected], sessions
        )
    finally:
        connection.close()
    report = settings.project_root / "data" / "validation-summary.json"
    _atomic_json(report, summary.model_dump(mode="json"))
    return {
        "symbols_checked": len(selected),
        "bars_checked": summary.checked_rows,
        "bars_rejected": summary.rejected_rows,
        "warnings": sum(issue.severity == "warning" for issue in summary.issues),
        "errors": sum(issue.severity == "error" for issue in summary.issues),
        "report_path": str(report),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="radar")
    parser.add_argument("--project-root", type=Path, default=Path.cwd())
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db")
    sync = commands.add_parser("sync")
    sync.add_argument("--end", type=date.fromisoformat)
    sync.add_argument("--lookback", type=int)
    sync.add_argument("--max-symbols", type=int)
    validate = commands.add_parser("validate")
    validate.add_argument("--end", type=date.fromisoformat)
    validate.add_argument("--lookback", type=int)
    validate.add_argument("--max-symbols", type=int)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    settings = load_settings(args.project_root)
    if args.command == "init-db":
        connection = get_connection(settings.database_path)
        connection.close()
        print(json.dumps({"database_path": str(settings.database_path), "schema_version": 1}))
        return 0
    end = args.end or (datetime.now(ZoneInfo("America/New_York")).date() - timedelta(days=1))
    key, secret = load_credentials(settings.project_root)
    provider = AlpacaProvider.from_credentials(key, secret)
    runner = run_sync if args.command == "sync" else run_validation
    result = runner(settings, provider, end=end, lookback=args.lookback, max_symbols=args.max_symbols)
    print(json.dumps(result, ensure_ascii=False))
    return 0

"""Backfill a separate local research database with existing Alpaca ingestion.

Run from the project root with the project's installed Python environment.
The live market.duckdb is copied once and is never opened for writing here.
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import date, datetime, timezone
from pathlib import Path

from radar.config import load_settings
from radar.daily_update import credentials, target_date
from radar.db import get_connection
from radar.ingestion.bars import ingest_daily_bars
from radar.providers.alpaca import AlpacaProvider


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_RESEARCH_DB = ROOT / "data" / "phase2-research.duckdb"


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill a separate Phase 2 research database")
    parser.add_argument("--database", type=Path, default=DEFAULT_RESEARCH_DB)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2021, 9, 1))
    parser.add_argument("--end", type=date.fromisoformat,
                        default=date.fromisoformat(target_date(datetime.now(timezone.utc))))
    parser.add_argument("--max-symbols", type=int)
    args = parser.parse_args()
    if args.start > args.end:
        parser.error("start must be on or before end")
    if args.max_symbols is not None and args.max_symbols < 1:
        parser.error("max-symbols must be positive")
    settings = load_settings(ROOT)
    database = args.database.resolve()
    if database == settings.database_path.resolve():
        parser.error("research database must differ from the live market database")
    if not settings.database_path.is_file():
        parser.error("live market database is missing")

    key, secret = credentials(ROOT)
    provider = AlpacaProvider.from_credentials(key, secret)
    sessions = provider.get_market_sessions(args.start, args.end)
    if not sessions:
        parser.error("selected dates contain no trading sessions")
    if not database.exists():
        database.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(settings.database_path, database)

    connection = get_connection(database)
    try:
        eligible = [row[0] for row in connection.execute("""
            WITH recent AS (
                SELECT symbol, AVG(close * volume) AS dollar_volume
                FROM daily_bars
                WHERE date >= (SELECT MAX(date) FROM daily_bars) - INTERVAL 35 DAY
                GROUP BY symbol
            )
            SELECT a.symbol FROM assets a
            LEFT JOIN recent r ON a.symbol = r.symbol
            WHERE upper(trim(a.asset_class)) = 'US_EQUITY'
              AND upper(trim(a.status)) = 'ACTIVE'
              AND a.tradable
              AND upper(trim(a.exchange)) IN ('NASDAQ', 'NYSE', 'AMEX', 'ARCA', 'BATS')
            ORDER BY r.dollar_volume DESC NULLS LAST, a.symbol
        """).fetchall()]
        selected = eligible[:args.max_symbols] if args.max_symbols else eligible
        selected = sorted(set(selected) | {"SPY", "QQQ"})
        result = ingest_daily_bars(
            connection, provider, selected, sessions,
            feed=settings.feed, adjustment=settings.adjustment,
        )
    finally:
        connection.close()
    print(json.dumps({
        "database": str(database), "session_start": sessions[0].isoformat(),
        "session_end": sessions[-1].isoformat(), "sessions": len(sessions),
        "symbols": len(selected), "provider": "alpaca", "feed": settings.feed,
        "adjustment": settings.adjustment, "inserted": result.inserted_rows,
        "updated": result.updated_rows, "rejected": result.rejected_rows,
        "batches": result.batch_count, "failed_symbols": result.failed_symbols,
        "issue_counts": {severity: sum(i.severity == severity for i in result.issues)
                         for severity in ("warning", "error")},
        "errors": [issue.model_dump(mode="json") for issue in result.issues
                   if issue.severity == "error"],
        "warning_examples": [issue.model_dump(mode="json") for issue in result.issues
                             if issue.severity == "warning"][:5],
    }, ensure_ascii=False))
    return 2 if result.failed_symbols or result.rejected_rows else 0


if __name__ == "__main__":
    raise SystemExit(main())

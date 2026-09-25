"""Offline command/config checks for the Phase 1 workflow."""

from __future__ import annotations

from datetime import date, datetime, timezone

from radar.app import run_sync, run_validation
from radar.config import Settings, load_credentials
from radar.db import get_connection
from radar.models import AssetRecord, DailyBar, ProviderBatchResult

UTC = timezone.utc
SESSIONS = [date(2024, 1, 2), date(2024, 1, 3)]


class OfflineProvider:
    bar_calls = 0

    def __init__(
        self,
        symbols: tuple[str, ...] = ("AAPL", "MSFT"),
        seen_at: datetime = datetime(2024, 1, 4, tzinfo=UTC),
    ) -> None:
        self.symbols = symbols
        self.seen_at = seen_at

    def get_assets(self):
        now = self.seen_at
        return [
            AssetRecord(
                symbol=symbol,
                name=symbol,
                exchange="NASDAQ",
                asset_class="us_equity",
                status="active",
                tradable=True,
                fractionable=False,
                shortable=False,
                easy_to_borrow=False,
                first_seen=now,
                last_seen=now,
                updated_at=now,
            )
            for symbol in self.symbols
        ]

    def get_market_sessions(self, start, end):
        return SESSIONS

    def get_daily_bars(self, symbols, start, end, feed, adjustment):
        self.bar_calls += 1
        bars = [
            DailyBar(
                symbol=symbol,
                date=day,
                open=10.0,
                high=11.0,
                low=9.0,
                close=10.5,
                volume=100,
                provider="alpaca",
                feed=feed,
                adjustment=adjustment,
                downloaded_at=datetime(2024, 1, 4, tzinfo=UTC),
            )
            for symbol in symbols
            for day in SESSIONS
            if start <= day <= end
        ]
        yield ProviderBatchResult(
            requested_symbols=list(symbols),
            bars=bars,
            provider="alpaca",
            feed=feed,
            start=start,
            end=end,
        )


def test_sync_exports_universe_and_only_fetches_missing_bars(tmp_path) -> None:
    settings = Settings(tmp_path, tmp_path / "data" / "market.duckdb", "sip", "split", 2)
    provider = OfflineProvider()
    first = run_sync(settings, provider, end=SESSIONS[-1], max_symbols=1)
    assert first["eligible_symbols"] == 2
    assert first["bars_inserted"] == 2
    assert provider.bar_calls == 1
    assert (tmp_path / "data" / "universe.csv").is_file()
    assert (tmp_path / "data" / "ingestion-issues.json").is_file()
    connection = get_connection(settings.database_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 2
        assert connection.execute("SELECT COUNT(*) FROM daily_bars").fetchone()[0] == 2
    finally:
        connection.close()
    second = run_sync(settings, provider, end=SESSIONS[-1], max_symbols=1)
    assert second["bars_fetched"] == 0
    assert provider.bar_calls == 1
    validation = run_validation(settings, provider, end=SESSIONS[-1], max_symbols=1)
    assert validation["bars_checked"] == 2
    assert validation["bars_rejected"] == 0
    assert (tmp_path / "data" / "validation-summary.json").is_file()


def test_validation_ignores_assets_absent_from_latest_snapshot(tmp_path) -> None:
    settings = Settings(tmp_path, tmp_path / "data" / "market.duckdb", "sip", "split", 2)
    first = OfflineProvider(("AAPL", "MSFT"), datetime(2024, 1, 4, tzinfo=UTC))
    run_sync(settings, first, end=SESSIONS[-1])
    second = OfflineProvider(("AAPL",), datetime(2024, 1, 5, tzinfo=UTC))
    run_sync(settings, second, end=SESSIONS[-1])
    validation = run_validation(settings, second, end=SESSIONS[-1])
    assert validation["symbols_checked"] == 1
    connection = get_connection(settings.database_path)
    try:
        assert connection.execute("SELECT COUNT(*) FROM assets").fetchone()[0] == 2
        assert connection.execute(
            """
            SELECT COUNT(*) FROM assets
            WHERE symbol = 'MSFT' AND last_seen < (SELECT MAX(last_seen) FROM assets)
            """
        ).fetchone()[0] == 1
    finally:
        connection.close()


def test_credentials_read_project_dotenv_without_mutating_environment(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ALPACA_API_KEY", raising=False)
    monkeypatch.delenv("ALPACA_SECRET_KEY", raising=False)
    (tmp_path / ".env").write_text(
        "ALPACA_API_KEY=fake-key\nALPACA_SECRET_KEY=fake-secret\n", encoding="utf-8"
    )
    assert load_credentials(tmp_path) == ("fake-key", "fake-secret")

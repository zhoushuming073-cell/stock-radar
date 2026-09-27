"""Calendar boundaries for the unattended after-close update."""

from datetime import datetime, timezone
from pathlib import Path

import pytest

from radar.daily_update import credentials, target_date


def test_target_date_after_us_close_during_daylight_time() -> None:
    # Friday 20:30 in New York is Saturday 08:30 in China.
    assert target_date(datetime(2026, 9, 26, 0, 30, tzinfo=timezone.utc)) == "2026-09-25"


def test_target_date_before_close_and_over_weekend() -> None:
    assert target_date(datetime(2026, 9, 25, 14, 0, tzinfo=timezone.utc)) == "2026-09-24"
    assert target_date(datetime(2026, 9, 27, 14, 0, tzinfo=timezone.utc)) == "2026-09-25"


def test_target_date_after_us_close_during_standard_time() -> None:
    assert target_date(datetime(2026, 12, 12, 0, 30, tzinfo=timezone.utc)) == "2026-12-11"


def test_credentials_use_existing_key_file_beside_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "stock-radar"
    project.mkdir()
    (tmp_path / "alpacakey.txt").write_text(
        "ALPACA_API_KEY=fake-key\nALPACA_SECRET_KEY=fake-secret\n", encoding="utf-8",
    )
    monkeypatch.setattr("radar.daily_update.load_credentials",
                        lambda _root: (_ for _ in ()).throw(ValueError("no .env")))
    assert credentials(project) == ("fake-key", "fake-secret")

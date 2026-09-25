"""Calendar boundaries for the unattended after-close update."""

from datetime import datetime, timezone

from radar.daily_update import target_date


def test_target_date_after_us_close_during_daylight_time() -> None:
    # Friday 20:30 in New York is Saturday 08:30 in China.
    assert target_date(datetime(2026, 9, 26, 0, 30, tzinfo=timezone.utc)) == "2026-09-25"


def test_target_date_before_close_and_over_weekend() -> None:
    assert target_date(datetime(2026, 9, 25, 14, 0, tzinfo=timezone.utc)) == "2026-09-24"
    assert target_date(datetime(2026, 9, 27, 14, 0, tzinfo=timezone.utc)) == "2026-09-25"


def test_target_date_after_us_close_during_standard_time() -> None:
    assert target_date(datetime(2026, 12, 12, 0, 30, tzinfo=timezone.utc)) == "2026-12-11"

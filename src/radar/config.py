"""Small, explicit loader for project settings and Alpaca credentials."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml
from dotenv import dotenv_values


@dataclass(frozen=True)
class Settings:
    project_root: Path
    database_path: Path
    feed: str
    adjustment: str
    lookback_sessions: int


def load_settings(project_root: Path, config_path: Path | None = None) -> Settings:
    root = project_root.resolve()
    config_file = config_path or root / "config" / "base.yaml"
    with config_file.open("r", encoding="utf-8") as stream:
        raw = yaml.safe_load(stream)
    if not isinstance(raw, dict) or raw.get("provider") != "alpaca":
        raise ValueError("config must select the alpaca provider")
    daily = raw.get("daily_bars")
    if not isinstance(daily, dict):
        raise ValueError("config.daily_bars must be a mapping")
    lookback = daily.get("lookback_sessions")
    if not isinstance(lookback, int) or isinstance(lookback, bool) or lookback < 1:
        raise ValueError("lookback_sessions must be a positive integer")
    env_file = root / ".env"
    local = dotenv_values(env_file) if env_file.is_file() else {}
    db_value = os.environ.get("RADAR_DB_PATH") or local.get("RADAR_DB_PATH") or raw.get("database_path")
    if not isinstance(db_value, str) or not db_value.strip():
        raise ValueError("database_path is required")
    db_path = Path(db_value)
    if not db_path.is_absolute():
        db_path = root / db_path
    feed = daily.get("feed")
    adjustment = daily.get("adjustment")
    if not isinstance(feed, str) or not feed.strip():
        raise ValueError("daily_bars.feed is required")
    if not isinstance(adjustment, str) or not adjustment.strip():
        raise ValueError("daily_bars.adjustment is required")
    return Settings(root, db_path, feed.strip(), adjustment.strip(), lookback)


def load_credentials(project_root: Path) -> tuple[str, str]:
    env_file = project_root / ".env"
    local = dotenv_values(env_file) if env_file.is_file() else {}
    key = os.environ.get("ALPACA_API_KEY") or local.get("ALPACA_API_KEY")
    secret = os.environ.get("ALPACA_SECRET_KEY") or local.get("ALPACA_SECRET_KEY")
    if not key or not secret:
        raise ValueError("ALPACA_API_KEY and ALPACA_SECRET_KEY must be set")
    return key, secret

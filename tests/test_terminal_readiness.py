"""Synthetic structural checks; they do not establish vendor completeness."""

import json

import pandas as pd
import pytest

from radar.lab.readiness import assess_readiness
from radar.lab.scanner import build_labels, evaluation_settings, primary_outcome_name
from radar.lab.terminal import EVENT_TYPES, LocalTerminalEvents
from radar.lab.universe import LocalSecurityMaster


def sources(tmp_path, *, event_type="cash_acquisition", cash="12", end="2024-01-03"):
    master_csv = tmp_path / "security-master.csv"
    master_csv.write_text(
        "security_id,symbol,valid_from,valid_to,listing_date,delisting_date,exchange,security_type,eligible\n"
        "S1,AAA,2024-01-01,2024-01-03,2024-01-01,2024-01-03,NASDAQ,common,true\n",
        encoding="utf-8")
    master_manifest = tmp_path / "security-master-manifest.json"
    master_manifest.write_text(json.dumps({"provider": "synthetic-fixture", "source_version": "1",
        "coverage_start": "2024-01-01", "coverage_end": end,
        "coverage_complete": True}), encoding="utf-8")
    event_csv = tmp_path / "terminal-events.csv"
    event_csv.write_text(
        "security_id,event_date,event_type,terminal_value_type,cash_per_share,stock_exchange_ratio,successor_security_id,final_trade_price,currency,known_complete,notes\n"
        f"S1,2024-01-03,{event_type},{'cash_per_share' if event_type == 'cash_acquisition' else 'unvalued'},{cash},,{('S1' if event_type == 'ticker_change' else '')},,USD,true,synthetic\n",
        encoding="utf-8")
    event_manifest = tmp_path / "terminal-events-manifest.json"
    event_manifest.write_text(json.dumps({"provider": "synthetic-fixture", "source_version": "1",
        "coverage_start": "2024-01-01", "coverage_end": end,
        "coverage_complete": True, "event_types_covered": sorted(EVENT_TYPES)}), encoding="utf-8")
    return LocalSecurityMaster(master_csv, master_manifest), LocalTerminalEvents(event_csv, event_manifest)


def test_terminal_import_cash_and_invalid_type(tmp_path):
    _, events = sources(tmp_path)
    event = events.event_on("S1", pd.Timestamp("2024-01-03"))
    assert event.settlement == 12
    event_csv = tmp_path / "terminal-events.csv"
    event_csv.write_text(event_csv.read_text().replace("cash_acquisition", "magic"), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown terminal event"):
        LocalTerminalEvents(event_csv, tmp_path / "terminal-events-manifest.json")


def test_ticker_change_preserves_identity(tmp_path):
    _, events = sources(tmp_path, event_type="ticker_change", cash="")
    assert events.event_on("S1", pd.Timestamp("2024-01-03")).continues_same_identity
    assert events.event_between("S1", pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")) is None


def test_scanner_terminal_cash_unknown_and_missing(tmp_path):
    _, terminal = sources(tmp_path)
    sessions = pd.date_range("2024-01-01", periods=3)
    bars = pd.DataFrame({"date": sessions[:2], "symbol": ["S1", "S1"],
                         "open": [10, 10], "high": [10, 10.5], "low": [10, 9.9]})
    signals = pd.DataFrame({"signal_date": [sessions[0]], "symbol": ["S1"]})
    settings = evaluation_settings({"horizon_sessions": 2})
    result = build_labels(signals, bars, sessions, settings, terminal_provider=terminal)
    assert result.iloc[0].label_status == "labeled"
    assert result.iloc[0].label[primary_outcome_name(settings)] is True
    assert result.iloc[0].label["terminal_return"] == pytest.approx(0.2)
    assert build_labels(signals, bars, sessions, settings).iloc[0].label_status == "censored"
    _, unknown = sources(tmp_path, event_type="delisting", cash="")
    result = build_labels(signals, bars, sessions, settings, terminal_provider=unknown)
    assert result.iloc[0].label_reason == "terminal_event_without_valued_outcome"


def test_formal_gate_requires_master_terminal_coverage_and_bars(tmp_path):
    master, terminal = sources(tmp_path)
    days = pd.date_range("2024-01-01", periods=3)
    bars = pd.DataFrame({"date": days[:2], "symbol": ["AAA", "AAA"],
                         "open": [10, 10], "high": [10, 11], "low": [9, 9], "close": [10, 10]})
    assert not assess_readiness("current_snapshot", days, master, terminal, bars)["formal_pit_ready"]
    assert not assess_readiness("point_in_time", days, master, None, bars)["formal_pit_ready"]
    ready = assess_readiness("point_in_time", days, master, terminal, bars)
    assert ready["formal_pit_ready"]
    assert ready["research_validity"] == "formal_pit_source_dependent"
    assert not assess_readiness("point_in_time", days.append(pd.DatetimeIndex(["2024-01-04"])),
                                master, terminal, bars)["formal_pit_ready"]
    _, unvalued = sources(tmp_path, event_type="delisting", cash="")
    assert not assess_readiness("point_in_time", days, master, unvalued, bars)["formal_pit_ready"]

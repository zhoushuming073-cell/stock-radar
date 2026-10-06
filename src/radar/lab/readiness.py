"""Formal PIT gate: source claims, structural checks, and observed bar coverage."""

from __future__ import annotations

from pathlib import Path
from typing import Sequence

import pandas as pd

from radar.lab.terminal import EVENT_TYPES, LocalTerminalEvents, load_terminal_events
from radar.lab.universe import LocalSecurityMaster


def assess_readiness(mode: str, sessions: Sequence[pd.Timestamp],
                     master: LocalSecurityMaster | None,
                     terminal: LocalTerminalEvents | None,
                     bars: pd.DataFrame | None = None) -> dict:
    days = pd.DatetimeIndex(sessions).normalize()
    report = {
        "research_validity": "exploratory_current_snapshot" if mode == "current_snapshot" else "pit_membership_only",
        "formal_pit_ready": False,
        "source_attested_completeness": False,
        "system_verified_structural_validity": False,
        "security_master": None,
        "historical_bar_coverage": {"expected": None, "observed": None, "missing": None},
        "terminal_events": None,
        "known_terminal_events": 0, "valued_terminal_events": 0,
        "unvalued_terminal_events": 0,
        "unmatched_master_delistings": 0,
        "terminal_value_policy": "terminal-cash-v1",
        "reasons": [],
    }
    if mode != "point_in_time":
        report["reasons"].append("Current Snapshot cannot establish historical universe membership")
        return report
    if master is None:
        report["reasons"].append("PIT Security Master is unavailable")
        return report
    report["security_master"] = master.provenance().metadata()
    if master.reconstructed:
        report["reasons"].append("open-source reconstructed membership is not source-attested complete")
        report["research_validity"] = "reconstructed_membership_exploratory"
    try:
        master.validate_coverage(days)
    except ValueError as error:
        report["reasons"].append(str(error))
        return report
    if not master.reconstructed:
        report["research_validity"] = "pit_with_censoring_audit"
    if terminal is None:
        report["reasons"].append("terminal-event provider is unavailable")
    else:
        report["terminal_events"] = {
            "provider": terminal.manifest["provider"],
            "source_version": terminal.manifest["source_version"],
            "coverage_start": str(terminal.coverage_start.date()),
            "coverage_end": str(terminal.coverage_end.date()),
            "fingerprint": terminal.fingerprint,
            "source_attested_complete": True,
            "event_types_covered": terminal.manifest["event_types_covered"],
        }
        if set(terminal.manifest["event_types_covered"]) != EVENT_TYPES:
            report["reasons"].append("terminal source does not attest all supported event types")
        events = [event for event in terminal.events.values()
                  if len(days) and days.min() <= event.event_date <= days.max()
                  and not event.continues_same_identity]
        report["known_terminal_events"] = len(events)
        report["valued_terminal_events"] = sum(event.settlement is not None for event in events)
        report["unvalued_terminal_events"] = len(events) - report["valued_terminal_events"]
        if report["unvalued_terminal_events"]:
            report["reasons"].append("known terminal events lack a supported economic settlement")
        try:
            terminal.validate_coverage(days)
            report["source_attested_completeness"] = True
        except ValueError as error:
            report["reasons"].append(str(error))
        for row in master.frame.itertuples(index=False):
            if pd.notna(row.delisting_date) and len(days) and days.min() <= row.delisting_date <= days.max():
                event = terminal.event_between(str(row.security_id), row.delisting_date,
                                               row.delisting_date)
                if event is None or event.settlement is None:
                    report["unmatched_master_delistings"] += 1
        if report["unmatched_master_delistings"]:
            report["reasons"].append("Security Master delistings lack valued terminal events")
    if bars is None:
        report["reasons"].append("historical bar coverage has not been checked")
    else:
        observed = master.filter_frame(bars)
        observed_pairs = set(zip(pd.to_datetime(observed["date"]).dt.normalize(),
                                 observed["security_id"].astype(str)))
        expected = {(day, str(row.security_id)) for day in days
                    for row in master.eligible_on(day).itertuples(index=False)
                    if terminal is None or not (
                        (event := terminal.event_on(str(row.security_id), day)) is not None
                        and event.settlement is not None)}
        missing = expected - observed_pairs
        report["historical_bar_coverage"] = {
            "expected": len(expected), "observed": len(expected) - len(missing),
            "missing": len(missing),
        }
        if missing:
            report["reasons"].append(f"{len(missing)} eligible security/session bars are missing")
    report["system_verified_structural_validity"] = not report["reasons"]
    report["formal_pit_ready"] = (report["source_attested_completeness"] and
                                  report["system_verified_structural_validity"])
    if report["formal_pit_ready"]:
        report["research_validity"] = "formal_pit_source_dependent"
    return report


def local_readiness(root: Path, mode: str, sessions: Sequence[pd.Timestamp]) -> dict:
    root = Path(root)
    master = None
    terminal = None
    errors = []
    if mode == "point_in_time":
        try:
            master = LocalSecurityMaster(root / "data/security-master.csv",
                                         root / "data/security-master-manifest.json")
        except (ValueError, OSError) as error:
            errors.append(str(error))
        try:
            terminal = load_terminal_events(root)
        except (ValueError, OSError) as error:
            errors.append(str(error))
    bars = None
    if master is not None and len(sessions):
        from radar.lab.data import load_forward_bars
        bars = load_forward_bars(root / "data/phase2-research.duckdb",
                                 min(sessions), max(sessions))
    report = assess_readiness(mode, sessions, master, terminal, bars)
    report["reasons"].extend(errors)
    if errors:
        report["formal_pit_ready"] = False
        report["system_verified_structural_validity"] = False
    return report

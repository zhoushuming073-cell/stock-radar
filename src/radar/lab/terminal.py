"""Source-attested terminal events; only explicit cash consideration is valued.

The CSV adapter validates structure. A manifest is a provenance claim by its
source, not independent proof that every historical event was supplied.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import math
from pathlib import Path
from typing import Protocol, Sequence

import pandas as pd


EVENT_TYPES = frozenset({"cash_acquisition", "stock_merger", "delisting",
                         "bankruptcy", "liquidation", "ticker_change",
                         "unknown_terminal_event"})
TERMINAL_POLICY = "terminal-cash-v1"
TERMINAL_LABEL_VERSION = "scanner-forward-v3-terminal"
REQUIRED = frozenset({"security_id", "event_date", "event_type", "terminal_value_type",
                      "cash_per_share", "stock_exchange_ratio", "successor_security_id",
                      "final_trade_price", "currency", "known_complete", "notes"})


@dataclass(frozen=True)
class TerminalEvent:
    security_id: str
    event_date: pd.Timestamp
    event_type: str
    terminal_value_type: str
    cash_per_share: float | None
    successor_security_id: str | None
    source: str
    source_version: str
    stock_exchange_ratio: float | None = None
    final_trade_price: float | None = None
    currency: str | None = None
    known_complete: bool = True
    notes: str | None = None

    @property
    def continues_same_identity(self) -> bool:
        return self.event_type == "ticker_change" and self.successor_security_id == self.security_id

    @property
    def settlement(self) -> float | None:
        if (self.event_type == "cash_acquisition" and
                self.terminal_value_type == "cash_per_share" and self.currency == "USD"):
            return self.cash_per_share
        return None


class TerminalEventProvider(Protocol):
    @property
    def fingerprint(self) -> str: ...

    def validate_coverage(self, sessions: Sequence[pd.Timestamp]) -> None: ...

    def event_on(self, security_id: str, date: pd.Timestamp) -> TerminalEvent | None: ...

    def event_between(self, security_id: str, first: pd.Timestamp,
                      last: pd.Timestamp) -> TerminalEvent | None: ...


class LocalTerminalEvents:
    """Import a source's event ledger and its explicit coverage declaration."""

    def __init__(self, csv_path: Path, manifest_path: Path) -> None:
        self.csv_path, self.manifest_path = Path(csv_path), Path(manifest_path)
        if not self.csv_path.is_file() or not self.manifest_path.is_file():
            raise ValueError("terminal-events.csv and terminal-events-manifest.json are required")
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        for key in ("provider", "source_version", "coverage_start", "coverage_end",
                    "coverage_complete", "event_types_covered"):
            if key not in self.manifest:
                raise ValueError(f"terminal manifest missing {key}")
        for key in ("provider", "source_version"):
            if not isinstance(self.manifest[key], str) or not self.manifest[key].strip():
                raise ValueError(f"terminal {key} must be nonempty")
        if self.manifest["coverage_complete"] is not True:
            raise ValueError("terminal source has not attested complete coverage")
        covered = self.manifest["event_types_covered"]
        if (not isinstance(covered, list) or not covered or
                len(set(covered)) != len(covered) or not set(covered) <= EVENT_TYPES):
            raise ValueError("terminal manifest has invalid event_types_covered")
        self.coverage_start = pd.Timestamp(self.manifest["coverage_start"]).normalize()
        self.coverage_end = pd.Timestamp(self.manifest["coverage_end"]).normalize()
        if self.coverage_start > self.coverage_end:
            raise ValueError("invalid terminal coverage interval")
        frame = pd.read_csv(self.csv_path, dtype={"security_id": str, "successor_security_id": str})
        missing = REQUIRED - set(frame)
        if missing:
            raise ValueError(f"terminal CSV missing columns: {sorted(missing)}")
        self.frame = frame
        self.events: dict[tuple[str, pd.Timestamp], TerminalEvent] = {}
        for row in frame.to_dict("records"):
            identity = str(row["security_id"]).strip()
            if not identity or identity.lower() == "nan":
                raise ValueError("terminal security_id must be nonempty")
            date = pd.to_datetime(row["event_date"], errors="coerce")
            if pd.isna(date):
                raise ValueError("invalid terminal event date")
            date = pd.Timestamp(date).normalize()
            if date < self.coverage_start or date > self.coverage_end:
                raise ValueError("terminal event date is outside manifest coverage")
            kind = str(row["event_type"])
            if kind not in EVENT_TYPES:
                raise ValueError(f"unknown terminal event type: {kind}")
            if kind not in covered:
                raise ValueError(f"terminal source did not attest event type: {kind}")
            value_type = str(row["terminal_value_type"] or "").strip()
            if value_type == "nan":
                value_type = ""
            def optional_nonnegative(field: str) -> float | None:
                raw = row[field]
                if pd.isna(raw):
                    return None
                try:
                    parsed = float(raw)
                except (TypeError, ValueError) as error:
                    raise ValueError(f"{field} must be numeric") from error
                if not math.isfinite(parsed) or parsed < 0:
                    raise ValueError(f"{field} must be finite and nonnegative")
                return parsed

            cash = optional_nonnegative("cash_per_share")
            ratio = optional_nonnegative("stock_exchange_ratio")
            last_price = optional_nonnegative("final_trade_price")
            if value_type not in {"", "unvalued", "cash_per_share"}:
                raise ValueError("unsupported terminal value type")
            if value_type == "cash_per_share" and (kind != "cash_acquisition" or cash is None):
                raise ValueError("cash settlement requires cash acquisition and cash_per_share")
            successor = None if pd.isna(row["successor_security_id"]) else str(row["successor_security_id"]).strip()
            if kind == "ticker_change" and successor != identity:
                raise ValueError("ticker_change must preserve the same security_id")
            if kind == "stock_merger" and (not successor or ratio is None or ratio <= 0):
                raise ValueError("stock merger requires successor_security_id and positive exchange ratio")
            if str(row["known_complete"]).lower() not in {"true", "1"}:
                raise ValueError("terminal record must be source-attested complete")
            currency = None if pd.isna(row["currency"]) else str(row["currency"]).strip().upper()
            if currency and (len(currency) != 3 or not currency.isalpha()):
                raise ValueError("terminal currency must be a three-letter code")
            if value_type == "cash_per_share" and not currency:
                raise ValueError("cash settlement requires an explicit currency")
            notes = None if pd.isna(row["notes"]) else str(row["notes"])
            event = TerminalEvent(identity, date, kind, value_type, cash, successor,
                                  self.manifest["provider"], self.manifest["source_version"],
                                  ratio, last_price, currency, True, notes)
            key = (identity, date)
            if key in self.events:
                raise ValueError("duplicate terminal event for security and date")
            self.events[key] = event
        self._fingerprint = hashlib.sha256(self.csv_path.read_bytes() + b"\0" +
                                           self.manifest_path.read_bytes()).hexdigest()

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def validate_coverage(self, sessions: Sequence[pd.Timestamp]) -> None:
        dates = pd.DatetimeIndex(sessions).normalize()
        if dates.empty or dates.min() < self.coverage_start or dates.max() > self.coverage_end:
            raise ValueError("terminal events do not cover the requested interval")

    def event_on(self, security_id: str, date: pd.Timestamp) -> TerminalEvent | None:
        return self.events.get((str(security_id), pd.Timestamp(date).normalize()))

    def event_between(self, security_id: str, first: pd.Timestamp,
                      last: pd.Timestamp) -> TerminalEvent | None:
        found = [event for (identity, date), event in self.events.items()
                 if identity == str(security_id) and first <= date <= last and
                 not event.continues_same_identity]
        return min(found, key=lambda event: event.event_date) if found else None


def load_terminal_events(root: Path) -> LocalTerminalEvents | None:
    csv = Path(root) / "data" / "terminal-events.csv"
    manifest = Path(root) / "data" / "terminal-events-manifest.json"
    if not csv.exists() and not manifest.exists():
        return None
    return LocalTerminalEvents(csv, manifest)

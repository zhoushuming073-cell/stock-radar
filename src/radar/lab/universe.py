"""Historical security-master boundary for research runs.

The local CSV adapter is format support, not a claim that a trustworthy PIT
source is installed. Coverage is attested by the imported manifest and checked
against every requested trading session.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Protocol, Sequence

import pandas as pd


REQUIRED_COLUMNS = frozenset({
    "security_id", "symbol", "valid_from", "valid_to", "listing_date",
    "delisting_date", "exchange", "security_type", "eligible",
})


class PointInTimeUniverseProvider(Protocol):
    @property
    def fingerprint(self) -> str: ...

    def validate_coverage(self, sessions: Sequence[pd.Timestamp]) -> None: ...

    def eligible_on(self, date: pd.Timestamp) -> pd.DataFrame: ...

    def filter_frame(self, frame: pd.DataFrame) -> pd.DataFrame: ...


@dataclass(frozen=True)
class UniverseProvenance:
    mode: str
    provider: str | None
    source_version: str | None
    fingerprint: str | None
    coverage_start: str | None
    coverage_end: str | None
    bias_risk: str
    feature_basis: str | None = None
    feature_store_sha256: str | None = None

    def metadata(self) -> dict:
        return self.__dict__.copy()


def validate_frozen_feature_store(provenance: UniverseProvenance, metadata: dict) -> None:
    """Semantic universe identity does not replace the queued artifact byte lock."""
    if provenance.mode == "point_in_time" and provenance.feature_store_sha256 != (
            metadata.get("universe_provenance") or {}).get("feature_store_sha256"):
        raise ValueError("queued PIT feature database changed")


def semantic_fingerprint(csv: bytes, manifest: dict, feature_store: dict | None) -> str:
    """Bind deterministic inputs; acquisition time and local paths are receipts.

    DuckDB file layout and reviewed reuse history are also artifact metadata.
    Workers separately freeze and verify the actual database SHA-256.
    """
    source = {k: v for k, v in manifest.items() if k not in {"built_at", "stock_radar_commit"}}
    features = None
    if feature_store is not None:
        features = {k: v for k, v in feature_store.items()
                    if k not in {"database", "database_sha256", "source_database", "reviewed_reuse"}}
        if "external_prices" in features:
            features["external_prices"] = {k: v for k, v in features["external_prices"].items()
                                            if k not in {"database", "database_sha256"}}
    payload = json.dumps({"policy": "pit-semantic-fingerprint-v1", "manifest": source,
                          "features": features}, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(csv + b"\0" + payload).hexdigest()


class LocalSecurityMaster:
    """Read an imported CSV plus an explicit source coverage manifest."""

    def __init__(self, csv_path: Path, manifest_path: Path) -> None:
        self.csv_path = Path(csv_path)
        self.manifest_path = Path(manifest_path)
        if not self.csv_path.is_file() or not self.manifest_path.is_file():
            raise ValueError("point-in-time mode requires security-master.csv and manifest.json")
        self.manifest = json.loads(self.manifest_path.read_text(encoding="utf-8"))
        for key in ("provider", "source_version", "coverage_start", "coverage_end",
                    "coverage_complete"):
            if key not in self.manifest:
                raise ValueError(f"security-master manifest missing {key}")
        self.reconstructed = self.manifest.get("reconstruction_kind") == "snapshot-interval-v1"
        if self.manifest["coverage_complete"] is not True and not self.reconstructed:
            raise ValueError("security-master source has not attested complete coverage")
        if self.reconstructed:
            if self.manifest["coverage_complete"] is not False or self.manifest.get("source_attested_completeness") is not False:
                raise ValueError("reconstructed membership cannot attest complete coverage")
            if hashlib.sha256(self.csv_path.read_bytes()).hexdigest() != self.manifest.get("output_sha256"):
                raise ValueError("security-master output hash mismatch")
            if not self.manifest.get("coverage_windows"):
                raise ValueError("reconstructed membership requires explicit coverage windows")
        for key in ("provider", "source_version"):
            if not isinstance(self.manifest[key], str) or not self.manifest[key].strip():
                raise ValueError(f"security-master {key} must be nonempty")
        self.coverage_start = pd.Timestamp(self.manifest["coverage_start"]).normalize()
        self.coverage_end = pd.Timestamp(self.manifest["coverage_end"]).normalize()
        if self.coverage_start > self.coverage_end:
            raise ValueError("invalid security-master coverage interval")
        # NA is a real ticker. Pandas' default NA vocabulary must not turn
        # security identifiers into missing values; dates are parsed below.
        self.frame = pd.read_csv(self.csv_path, dtype={"security_id": str, "symbol": str},
                                 keep_default_na=False)
        missing = REQUIRED_COLUMNS - set(self.frame)
        if missing:
            raise ValueError(f"security-master CSV missing columns: {sorted(missing)}")
        if self.frame.empty:
            raise ValueError("security-master CSV is empty")
        for key in ("security_id", "symbol", "exchange", "security_type"):
            if self.frame[key].isna().any() or self.frame[key].astype(str).str.strip().eq("").any():
                raise ValueError(f"security-master {key} must be nonempty")
        for key in ("valid_from", "valid_to", "listing_date", "delisting_date"):
            source = self.frame[key].astype("string").str.strip()
            blank = source.isna() | source.eq("")
            parsed = pd.to_datetime(source.where(~blank), errors="coerce").dt.normalize()
            if (parsed.isna() & ~blank).any():
                raise ValueError(f"security-master {key} contains an invalid date")
            self.frame[key] = parsed
        if self.frame["valid_from"].isna().any():
            raise ValueError("security-master valid_from must be a date")
        if self.frame["valid_to"].notna().any() and (
                self.frame.loc[self.frame["valid_to"].notna(), "valid_to"] <
                self.frame.loc[self.frame["valid_to"].notna(), "valid_from"]).any():
            raise ValueError("security-master valid_to precedes valid_from")
        dated = self.frame["listing_date"].notna() & self.frame["delisting_date"].notna()
        if (self.frame.loc[dated, "listing_date"] >
                self.frame.loc[dated, "delisting_date"]).any():
            raise ValueError("security-master delisting_date precedes listing_date")
        flags = self.frame["eligible"].astype(str).str.lower()
        if not flags.isin({"true", "false", "1", "0"}).all():
            raise ValueError("security-master eligible must be true/false")
        self.frame["eligible"] = flags.isin({"true", "1"})
        self._validate_intervals()
        self.feature_store = None
        sidecar = self.csv_path.with_name("security-master-feature-store.json")
        if sidecar.exists():
            self.feature_store = json.loads(sidecar.read_text(encoding="utf-8"))
            if self.feature_store.get("master_output_sha256") != hashlib.sha256(self.csv_path.read_bytes()).hexdigest():
                raise ValueError("PIT feature store is bound to another security master")
        self._fingerprint = semantic_fingerprint(
            self.csv_path.read_bytes(), self.manifest, self.feature_store)

    @property
    def fingerprint(self) -> str:
        return self._fingerprint

    def _validate_intervals(self) -> None:
        # A ticker may be reused, but never by two security IDs on one date.
        for key, label in (("symbol", "symbol"), ("security_id", "security identity")):
            ordered = self.frame.sort_values([key, "valid_from"], kind="stable")
            ends = ordered.valid_to.fillna(pd.Timestamp.max.normalize())
            prior_end = ends.groupby(ordered[key], sort=False).shift()
            overlap = ordered.valid_from.le(prior_end)
            if overlap.any():
                raise ValueError(f"overlapping {label} mappings: {ordered.loc[overlap, key].iloc[0]}")

    def eligible_on(self, date: pd.Timestamp) -> pd.DataFrame:
        rows = self.observed_on(date)
        return rows.loc[rows["eligible"]].copy()

    def observed_on(self, date: pd.Timestamp) -> pd.DataFrame:
        """Return observed instruments, retaining unknown/ineligible types."""
        day = pd.Timestamp(date).normalize()
        if pd.isna(day) or day < self.coverage_start or day > self.coverage_end:
            raise ValueError("PIT date is outside source coverage")
        if self.reconstructed and not any(
                pd.Timestamp(first) <= day <= pd.Timestamp(last)
                for first, last in self.manifest["coverage_windows"]):
            raise ValueError(f"PIT source gap on {day.date()}")
        rows = self.frame[
            self.frame["valid_from"].le(day) &
            (self.frame["valid_to"].isna() | self.frame["valid_to"].ge(day)) &
            (self.frame["listing_date"].isna() | self.frame["listing_date"].le(day)) &
            (self.frame["delisting_date"].isna() | self.frame["delisting_date"].ge(day))
        ]
        return rows.copy()

    def validate_coverage(self, sessions: Sequence[pd.Timestamp]) -> None:
        days = pd.DatetimeIndex(sessions).normalize()
        if len(days) == 0:
            raise ValueError("PIT coverage requires trading sessions")
        if days.min() < self.coverage_start or days.max() > self.coverage_end:
            raise ValueError("PIT data does not cover the full requested interval")
        missing = [str(day.date()) for day in days if self.eligible_on(day).empty]
        if missing:
            raise ValueError(f"PIT data gap: no eligible securities on {missing[0]}")

    def filter_frame(self, frame: pd.DataFrame) -> pd.DataFrame:
        if frame.empty:
            return frame.copy()
        source = frame.reset_index(drop=True).copy()
        source["date"] = pd.to_datetime(source["date"]).dt.normalize()
        for day in source["date"].unique():
            self.observed_on(day)
        if "security_id" in source:
            source = source.rename(columns={"security_id": "_input_security_id"})
        source = source.drop(columns=["security_name"], errors="ignore")
        name_column = ["security_name"] if "security_name" in self.frame else []
        master = self.frame.loc[self.frame["eligible"],
                                ["security_id", "symbol", "valid_from", "valid_to",
                                 "listing_date", "delisting_date", *name_column]]
        result = source.merge(master, on="symbol", how="inner", validate="many_to_many")
        day = result["date"]
        result = result.loc[
            result["valid_from"].le(day) &
            (result["valid_to"].isna() | result["valid_to"].ge(day)) &
            (result["listing_date"].isna() | result["listing_date"].le(day)) &
            (result["delisting_date"].isna() | result["delisting_date"].ge(day))
        ].copy()
        if "_input_security_id" in result:
            if result["_input_security_id"].ne(result["security_id"]).any():
                raise ValueError("price/feature security identity differs from PIT mapping")
            result = result.drop(columns="_input_security_id")
        if result.duplicated(["date", "symbol"]).any():
            raise ValueError("ambiguous PIT security mapping for date and symbol")
        result = result.drop(columns=["valid_from", "valid_to",
                                      "listing_date", "delisting_date"])
        if "security_name" not in result:
            result["security_name"] = result["symbol"]
        else:
            result["security_name"] = result["security_name"].fillna(result["symbol"])
        return result.set_index(["date", "symbol"], drop=False).sort_index()

    def provenance(self) -> UniverseProvenance:
        return UniverseProvenance(
            mode="point_in_time", provider=str(self.manifest["provider"]),
            source_version=str(self.manifest["source_version"]),
            fingerprint=self.fingerprint,
            coverage_start=str(self.coverage_start.date()),
            coverage_end=str(self.coverage_end.date()),
            bias_risk="source_dependent_incomplete" if self.reconstructed else "source_dependent",
            feature_basis=(self.feature_store or {}).get("feature_basis"),
            feature_store_sha256=(self.feature_store or {}).get("database_sha256"))


def current_snapshot_provenance() -> UniverseProvenance:
    return UniverseProvenance(
        mode="current_snapshot", provider=None, source_version=None,
        fingerprint=None, coverage_start=None, coverage_end=None,
        bias_risk="present")


def load_universe(root: Path, mode: str, sessions: Sequence[pd.Timestamp]
                  ) -> tuple[LocalSecurityMaster | None, UniverseProvenance]:
    if mode == "research_infrastructure_v1":
        from radar.lab.research_backend import ResearchHistory, MODE
        with ResearchHistory(root) as history:
            if sessions and pd.Timestamp(max(sessions)) >= pd.Timestamp(
                    history.api.profile["semantics"]["fresh_start"]):
                raise ValueError("Research Infrastructure v1 historical mode excludes Fresh")
            provenance = UniverseProvenance(
                mode=MODE, provider="shape_research_universe_v1",
                source_version="research-infrastructure-v1",
                fingerprint=history.fingerprint,
                coverage_start=history.api.profile["semantics"]["frozen_splits"]["train"][0],
                coverage_end=history.api.profile["semantics"]["frozen_splits"]["test"][1],
                bias_risk="reduced_not_eliminated; unknown membership excluded",
                feature_basis="historical security_id; Alpaca SIP split OHLCV; SPY SIP split benchmark",
                feature_store_sha256=history.database_sha256)
        return None, provenance
    if mode == "current_snapshot":
        return None, current_snapshot_provenance()
    if mode != "point_in_time":
        raise ValueError(f"unknown universe mode: {mode}")
    provider = LocalSecurityMaster(
        Path(root) / "data" / "security-master.csv",
        Path(root) / "data" / "security-master-manifest.json")
    provider.validate_coverage(sessions)
    return provider, provider.provenance()

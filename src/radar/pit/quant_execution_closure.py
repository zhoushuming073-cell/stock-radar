"""Read-only dependency audits for an existing frozen Quant execution study.

Acquisition completeness is not identity or price acceptance. This module never
edits a Shape database, changes candidate selection or supplies execution bars.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from radar.research.sessions import calendar

OHLCV = ("open", "high", "low", "close", "volume")


def artifact_hash(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def required_sessions(decisions: list[str], window: list[str]) -> dict:
    """Each selected T requires every T+1..T+10 bar, without refill or pruning."""
    if len(window) != 3 or not window[0] <= window[1] < window[2]:
        raise ValueError("invalid frozen signal/execution interval")
    days = [str(d.date()) for d in calendar().sessions_in_range(window[0], window[2])]
    result = {}
    for decision in decisions:
        if decision not in days or not window[0] <= decision <= window[1]:
            raise ValueError("decision outside registered signal sessions")
        i = days.index(decision)
        hold = days[i + 1:i + 11]
        if len(hold) != 10:
            raise ValueError("incomplete reserved execution horizon")
        result[decision] = {"entry": hold[0], "exit": hold[-1], "sessions": hold}
    return result


def inspect_bars(frame: pd.DataFrame, required: list[str], *, source: str, basis: str) -> dict:
    """Describe defects, preserving halted/missing days instead of filling them."""
    if required != sorted(set(required)) or not required:
        raise ValueError("unique ordered required session labels required")
    if basis not in {"raw", "split"} or not source:
        raise ValueError("explicit homogeneous provenance required")
    if not {"date", "source", "basis", *OHLCV} <= set(frame):
        raise ValueError("incomplete price/provenance schema")
    f = frame.copy()
    f["date"] = pd.to_datetime(f.date).dt.strftime("%Y-%m-%d")
    f = f.loc[f.date.isin(required)]
    if f.date.duplicated().any():
        raise ValueError("duplicate dependency dates")
    a = f[list(OHLCV)].astype(float)
    invalid = (~np.isfinite(a).all(axis=1) | a.low.le(0) | a.volume.lt(0)
               | a.volume.ne(np.floor(a.volume))
               | ~a.open.between(a.low, a.high) | ~a.close.between(a.low, a.high))
    unsafe = invalid.copy()
    if "shape_research_ready" in f:
        unsafe |= ~f.shape_research_ready.fillna(False).astype(bool)
    for key in ("identity_conflict", "class_or_name_boundary", "future_leakage"):
        if key in f:
            unsafe |= f[key].fillna(True).astype(bool)
    homogeneous = bool(f.source.eq(source).all() and f.basis.eq(basis).all())
    missing = sorted(set(required) - set(f.date))
    return {"required": len(required), "available": len(f), "missing": missing,
            "unsafe": sorted(f.loc[unsafe, "date"].tolist()),
            "homogeneous_expected_source_basis": homogeneous,
            "coverage_and_sanity_complete": not missing and not unsafe.any() and homogeneous,
            "trust_acceptance": "NOT_ASSERTED"}


def compare_overlap(existing: pd.DataFrame, incoming: pd.DataFrame) -> dict:
    """All OHLCV cells matter; matching closes alone do not prove equivalence."""
    for f in (existing, incoming):
        if not {"date", *OHLCV} <= set(f):
            raise ValueError("OHLCV overlap requires the complete schema")
    left, right = existing.copy(), incoming.copy()
    for f in (left, right):
        f["date"] = pd.to_datetime(f.date).dt.strftime("%Y-%m-%d")
        if f.date.duplicated().any():
            raise ValueError("overlap has duplicate daily sessions")
    merged = left[["date", *OHLCV]].merge(right[["date", *OHLCV]], on="date", suffixes=("_old", "_new"))
    matches = {k: bool(len(merged) and np.array_equal(merged[k + "_old"].astype(float),
                                                    merged[k + "_new"].astype(float))) for k in OHLCV}
    return {"overlap_sessions": len(merged), "exact_by_field": matches,
            "all_ohlcv_exact": bool(len(merged) and all(matches.values()))}


def verify_acquisition(directory: Path, receipt: dict) -> bytes:
    """Hash-check privately captured evidence; containment prevents path escape."""
    directory = Path(directory).resolve()
    path = Path(receipt["file"])
    if not path.is_absolute():
        path = directory / path
    path = path.resolve()
    if not path.is_relative_to(directory) or artifact_hash(path) != receipt["raw_sha256"]:
        raise ValueError("acquisition evidence path/hash mismatch")
    return path.read_bytes()


def worksheet(connection, rows: list[dict], window: list[str], failures: list[dict]) -> list[dict]:
    """Recover exact private dependencies from selected signals and frozen prices."""
    selected = [r for r in rows if r["method"] == "q1_fuzzy_shape" and r["selected"]]
    results = []
    for failure in failures:
        sid = failure.get("security_id")
        if not sid:
            raise ValueError("security-scoped closure cannot resolve a global failure")
        items = [r for r in selected if r["security_id"] == sid]
        if not items:
            raise ValueError("blocker not in frozen selected signals")
        sources = {r["provenance"]["series_id"] for r in items}
        if len(sources) != 1:
            raise ValueError("selected signals contain an execution source switch")
        provenance = items[0]["provenance"]
        requirements = required_sessions([r["decision_date"] for r in items], window)
        required = sorted({d for r in requirements.values() for d in r["sessions"]})
        frame = connection.execute("SELECT * FROM shape_price WHERE series_id=? AND date BETWEEN ? AND ? ORDER BY date",
                                   [next(iter(sources)), window[0], window[2]]).df()
        check = inspect_bars(frame, required, source=provenance["source"], basis=provenance["basis"])
        unsafe = frame.loc[frame.date.dt.strftime("%Y-%m-%d").isin(check["unsafe"])]
        results.append({"security_id": sid, "historical_symbol": items[0]["symbol"],
                        "gate_reason": failure["reason"], "requirements": requirements,
                        "provenance": provenance, "price_check": check,
                        "unsafe_records": json.loads(unsafe.to_json(orient="records", date_format="iso")),
                        "accepted_supplement": False})
    return results


def public_summary(private_records: list[dict]) -> dict:
    """An allowlist, never a recursive dump of identity-bearing source evidence."""
    return {"dependency_count": len(private_records),
            "accepted_supplements": sum(r.get("accepted_supplement") is True for r in private_records),
            "missing_session_count": sum(len(r["price_check"]["missing"]) for r in private_records),
            "unsafe_session_count": sum(len(r["price_check"]["unsafe"]) for r in private_records),
            "reason_counts": {reason: sum(r["gate_reason"] == reason for r in private_records)
                              for reason in sorted({r["gate_reason"] for r in private_records})},
            "status": "BLOCKED" if any(not r.get("accepted_supplement") for r in private_records) else "NO_OPEN_DEPENDENCIES"}

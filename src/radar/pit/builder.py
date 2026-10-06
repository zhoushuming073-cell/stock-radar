"""Conservative interval reconstruction with explicit uncertainty.

Observed presence is not an IPO date; disappearance is not a delisting event.
Absent identity evidence creates distinct episodes, never guessed merges.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re

import pandas as pd

from radar.pit.sources import Snapshot

IMPORTER_VERSION = "snapshot-interval-v1"
CORE = ["security_id", "symbol", "valid_from", "valid_to", "listing_date",
        "delisting_date", "exchange", "security_type", "eligible", "security_name"]
TYPES = {"common stock": "common", "common": "common", "ordinary shares": "common",
         "etf": "etf", "etn": "etn", "preferred": "preferred", "warrant": "warrant",
         "unit": "unit", "rights": "rights", "closed-end fund": "closed_end_fund",
         "adr": "adr", "test": "test", "spac": "spac", "other": "other"}


def classify(record: dict) -> tuple[str, str, str]:
    """Prefer source-native flags; explicit instrument descriptions are inferred.

    A plain company name (or today's CIK) cannot establish historical type.
    The fallback matches instrument descriptions, not arbitrary ETF substrings.
    """
    if str(record.get("Test Issue", "")).upper() == "Y":
        return "test", "verified", "source_flag:Test Issue"
    for field in ("security_type", "securityType", "instrument_type"):
        value = str(record.get(field, "")).strip().lower()
        if value in TYPES:
            return TYPES[value], "verified", f"source_field:{field}"
    if str(record.get("ETF", "")).upper() == "Y":
        return "etf", "verified", "source_flag:ETF"
    name = str(record.get("name", record.get("Security Name", "")))
    if str(record.get("industry", "")).strip().lower() == "blank checks":
        return "spac", "inferred", "source_industry:Blank Checks"
    descriptors = [
        (r"\b(?:warrants?|warrant rights)\b", "warrant"),
        (r"\b(?:preferred (?:stock|shares)|depositary shares.*preferred)\b", "preferred"),
        (r"\b(?:units? consisting|units? each consisting|units? expiring)\b", "unit"),
        (r"(?:\bunits?$|\bunits? -)", "unit"),
        (r"\brights(?: to| expiring|$)\b", "rights"),
        (r"\b(?:exchange traded notes?|exchange-traded notes?|ETNs?)\b", "etn"),
        (r"\b(?:exchange traded funds?|exchange-traded funds?|ETF)\b", "etf"),
        (r"\b(?:closed[- ]end fund)\b", "closed_end_fund"),
        (r"\b(?:American (?:depositary|depository) (?:shares|receipts)|ADR|ADS)\b", "adr"),
        (r"\b(?:common stock|common shares?|ordinary shares?)\b", "common"),
    ]
    for pattern, kind in descriptors:
        if re.search(pattern, name, re.I):
            return kind, "inferred", "explicit_instrument_description"
    return "unknown", "unresolved", "no_native_type_or_instrument_description"


def digest(value) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"),
                                     ensure_ascii=False).encode()).hexdigest()


def load_identity_evidence(path: Path | None) -> list[dict]:
    """Only explicitly dated, documented security-level mappings may merge IDs.

    CIK is issuer identity; multi-class instruments need separate security IDs.
    Undated rename caches are candidate evidence, not verified mappings.
    """
    if path is None:
        return []
    rows = json.loads(path.read_text(encoding="utf-8"))
    for row in rows:
        for key in ("security_id", "symbol", "valid_from", "valid_to", "evidence_url",
                    "resolution_status", "identity_resolution_method"):
            if not row.get(key):
                raise ValueError(f"identity evidence missing {key}")
        if row["resolution_status"] != "verified":
            raise ValueError("unverified identity evidence cannot merge securities")
        first, last = date.fromisoformat(row["valid_from"]), date.fromisoformat(row["valid_to"])
        if first > last:
            raise ValueError("identity evidence interval is reversed")
    for i, row in enumerate(rows):
        for other in rows[i + 1:]:
            overlaps = max(row["valid_from"], other["valid_from"]) <= min(row["valid_to"], other["valid_to"])
            if overlaps and (row["symbol"] == other["symbol"] or row["security_id"] == other["security_id"]):
                raise ValueError("overlapping identity evidence")
    return rows


def reconstruct(snapshots, start: date, end: date, *, max_stale_days: int = 4,
                eligible_types: tuple[str, ...] = ("common",),
                identity_evidence: list[dict] | None = None) -> tuple[pd.DataFrame, dict]:
    if start > end or max_stale_days < 0:
        raise ValueError("invalid reconstruction bounds")
    evidence = identity_evidence or []
    rows, active, index, anomalies = [], {}, [], []
    previous_day, previous_count = None, None
    observed_days, valid_windows = [], []
    last_day = None
    for snapshot in snapshots:
        if last_day is not None and snapshot.day <= last_day:
            raise ValueError("snapshot dates must strictly increase")
        last_day = snapshot.day
        if snapshot.day > end:
            continue
        item = {"date": str(snapshot.day), "commit": snapshot.commit,
                "available_at": snapshot.available_at, "file_hashes": snapshot.hashes,
                "errors": list(snapshot.errors), "count": len(snapshot.records)}
        index.append(item)
        counts = Counter(r["exchange"] for r in snapshot.records)
        symbols = [r["symbol"] for r in snapshot.records]
        invalid = (snapshot.errors or not snapshot.records or len(symbols) != len(set(symbols)) or
                   set(counts) != {"NASDAQ", "NYSE", "AMEX"})
        # Massive source failure must never look like thousands of delistings.
        jump = (previous_count is not None and
                abs(len(symbols) - previous_count) / previous_count > .15)
        if invalid or jump:
            item["accepted"] = False
            item["errors"].append("invalid_or_abnormal_universe_jump")
            anomalies.append({"date": str(snapshot.day), "reason": item["errors"]})
            # Stop bounded carry on a known failure date, but do not fabricate
            # disappearance events or extend through the failed observation.
            for row in active.values():
                row["valid_to"] = min(row["valid_to"], str(snapshot.day - timedelta(days=1)))
            valid_windows = [(a, min(b, snapshot.day - timedelta(days=1))) for a, b in valid_windows]
            active = {}
            continue
        item["accepted"] = True
        observed_days.append(snapshot.day)
        valid_windows.append((max(start, snapshot.day), min(end, snapshot.day + timedelta(days=max_stale_days))))
        continuous = previous_day is not None and (snapshot.day - previous_day).days <= max_stale_days + 1
        present = set(symbols)
        for symbol, row in list(active.items()):
            if symbol not in present or not continuous:
                row["valid_to"] = min(row["valid_to"], str(snapshot.day - timedelta(days=1)))
                del active[symbol]
        type_counts = Counter()
        for record in snapshot.records:
            symbol = record["symbol"]
            name = str(record.get("name", record.get("Security Name", symbol))).strip()
            kind, type_status, type_method = classify(record)
            type_counts[kind] += 1
            matches = [r for r in evidence if r["symbol"] == symbol and
                       r["valid_from"] <= str(snapshot.day) <= r["valid_to"] and
                       (not r.get("observed_name_pattern") or
                        re.search(r["observed_name_pattern"], name, re.I))]
            mapping = matches[0] if matches else None
            old = active.get(symbol)
            same_identity = old is not None and (old["security_name"] == name or
                           (mapping and old["security_id"] == mapping["security_id"]))
            unchanged = same_identity and old["exchange"] == record["exchange"] and old["security_type"] == kind
            if unchanged:
                old["valid_to"] = str(min(end, snapshot.day + timedelta(days=max_stale_days)))
                old["last_source_commit"] = snapshot.commit
                old["last_observed_date"] = str(snapshot.day)
                continue
            if old is not None:
                old["valid_to"] = min(old["valid_to"], str(snapshot.day - timedelta(days=1)))
            identity = (mapping["security_id"] if mapping else old["security_id"] if same_identity else
                        "OBS-" + digest([symbol, str(snapshot.day), snapshot.commit, name])[:24])
            row = {
                "security_id": identity, "symbol": symbol,
                "valid_from": str(max(start, snapshot.day)),
                "valid_to": str(min(end, snapshot.day + timedelta(days=max_stale_days))),
                # Observation bounds must not be misrepresented as actual listing events.
                "listing_date": mapping.get("listing_date", "") if mapping else "",
                "delisting_date": mapping.get("delisting_date", "") if mapping else "",
                "exchange": record["exchange"], "security_type": kind,
                "eligible": kind in eligible_types, "security_name": name,
                "resolution_status": "verified" if mapping else "unresolved",
                "identity_resolution_method": mapping["identity_resolution_method"] if mapping else "observed_listing_episode",
                "identity_evidence_url": mapping["evidence_url"] if mapping else "",
                "type_resolution_status": type_status, "type_method": type_method,
                "membership_status": "inferred", "first_source_commit": snapshot.commit,
                "last_source_commit": snapshot.commit, "first_observed_date": str(snapshot.day),
                "last_observed_date": str(snapshot.day),
            }
            rows.append(row)
            active[symbol] = row
        item["exchange_counts"] = dict(counts)
        item["security_type_counts"] = dict(type_counts)
        previous_day, previous_count = snapshot.day, len(symbols)
    frame = pd.DataFrame([r for r in rows if r["valid_from"] <= r["valid_to"]])
    if frame.empty:
        raise ValueError("no usable historical snapshots")
    frame = frame.sort_values(["symbol", "valid_from", "security_id"], kind="stable").reset_index(drop=True)
    # Coverage windows are merged, independently of whether type filtering leaves
    # any eligible securities. Gaps remain gaps, not delisting dates.
    windows = []
    for first, last in sorted(valid_windows):
        if first > last:
            continue
        if windows and first <= windows[-1][1] + timedelta(days=1):
            windows[-1] = (windows[-1][0], max(last, windows[-1][1]))
        else:
            windows.append((first, last))
    gaps, cursor = [], start
    for first, last in windows:
        if cursor < first:
            gaps.append([str(cursor), str(first - timedelta(days=1))])
        cursor = last + timedelta(days=1)
    if cursor <= end:
        gaps.append([str(cursor), str(end)])
    report = {"snapshots": index, "source_gaps": gaps, "anomalies": anomalies,
              "coverage_windows": [[str(a), str(b)] for a, b in windows],
              "missing_snapshot_dates": [str(day.date()) for day in pd.date_range(start, end)
                                         if day.date() not in observed_days],
              "intervals": len(frame), "security_ids": frame.security_id.nunique(),
              "unresolved_intervals": int(frame.resolution_status.ne("verified").sum()),
              "unknown_type_intervals": int(frame.security_type.eq("unknown").sum())}
    return frame, report


def apply_verified_evidence(frame: pd.DataFrame, evidence: list[dict], *, max_stale_days: int = 4) -> tuple[pd.DataFrame, list[dict]]:
    """Documented identity/class events can correct a nearby lagging snapshot.

    Name-scoped authoritative boundaries do not swallow an unrelated issuer
    reusing the same ticker. Corrections remain inspectable beside raw evidence.
    """
    frame = frame.copy()
    conflicts = []
    for mapping in evidence:
        matches = frame.symbol.eq(mapping["symbol"])
        if mapping.get("observed_name_pattern"):
            matches &= frame.security_name.str.contains(mapping["observed_name_pattern"], regex=True, case=False)
        elif mapping.get("authoritative_symbol_interval"):
            raise ValueError("authoritative symbol bounds require issuer/class name scope")
        first, last = mapping["valid_from"], mapping["valid_to"]
        overlaps = matches & frame.valid_from.le(last) & frame.valid_to.ge(first)
        if mapping.get("authoritative_symbol_interval"):
            outside = matches & ~overlaps
            for row in frame.loc[outside].to_dict("records"):
                conflicts.append({"symbol": row["symbol"], "from": row["valid_from"], "to": row["valid_to"],
                                  "reason": "observation outside verified issuer/class symbol interval",
                                  "evidence_url": mapping["evidence_url"]})
            frame = frame.loc[~outside].copy()
            overlaps = overlaps.loc[frame.index]
        for index in frame.index[overlaps]:
            row = frame.loc[index]
            new_first, new_last = max(row.valid_from, first), min(row.valid_to, last)
            if (new_first, new_last) != (row.valid_from, row.valid_to):
                conflicts.append({"symbol": row.symbol, "from": row.valid_from, "to": row.valid_to,
                                  "corrected_from": new_first, "corrected_to": new_last,
                                  "reason": "verified effective symbol boundary", "evidence_url": mapping["evidence_url"]})
            frame.loc[index, ["valid_from", "valid_to", "security_id", "resolution_status",
                              "identity_resolution_method", "identity_evidence_url"]] = [
                new_first, new_last, mapping["security_id"], "verified",
                mapping["identity_resolution_method"], mapping["evidence_url"]]
        if mapping.get("extend_first_observation") and overlaps.any():
            index = frame.loc[overlaps].valid_from.idxmin()
            delta = (date.fromisoformat(frame.loc[index, "valid_from"]) - date.fromisoformat(first)).days
            if 0 < delta <= max_stale_days:
                conflicts.append({"symbol": mapping["symbol"], "reason": "official effective date precedes nearby screener observation",
                                  "corrected_from": first, "evidence_url": mapping["evidence_url"]})
                frame.loc[index, "valid_from"] = first
                frame.loc[index, "membership_status"] = "verified_effective_date"
    return frame.sort_values(["symbol", "valid_from", "security_id"], kind="stable").reset_index(drop=True), conflicts


def write_build(output: Path, frame: pd.DataFrame, report: dict, *, start: date,
                end: date, source_pins: dict, stock_radar_commit: str,
                max_stale_days: int = 4, identity_evidence: list[dict] | None = None) -> dict:
    """Write an immutable content-addressed build; never replace installed data."""
    payload = frame.to_csv(index=False, lineterminator="\n").encode("utf-8")
    output_hash = hashlib.sha256(payload).hexdigest()
    importer_hashes = {path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                       for path in (Path(__file__), Path(__file__).with_name("sources.py"))}
    content = {"importer_version": IMPORTER_VERSION, "source_pins": source_pins,
               "start": str(start), "end": str(end), "max_stale_days": max_stale_days,
               "output_sha256": output_hash, "identity_evidence": identity_evidence or [],
               "snapshot_index_sha256": digest(report["snapshots"]),
               "importer_source_sha256": importer_hashes}
    version = digest(content)
    manifest = {
        "provider": "rreichel3/US-Stock-Symbols historical Git snapshots",
        "source_version": version, "coverage_start": str(start), "coverage_end": str(end),
        "coverage_complete": False, "reconstruction_kind": IMPORTER_VERSION,
        "source_attested_completeness": False, "research_validity": "reconstructed_membership_exploratory",
        "survivorship_bias_risk": "source_dependent_incomplete", "coverage_windows": report["coverage_windows"],
        "source_gaps": report["source_gaps"], "max_stale_days": max_stale_days,
        "eligible_security_types": ["common"], "unknown_types_eligible": False,
        "identity_policy": "unresolved episodes remain separate; verified dated evidence only merges",
        "type_policy": "native fields first; explicit descriptions inferred; unknown excluded",
        "output_sha256": output_hash, "stock_radar_commit": stock_radar_commit,
        "built_at": datetime.now(timezone.utc).isoformat(), "build_inputs": content,
        "unresolved_records": report["unresolved_intervals"],
    }
    build = output / version
    if build.exists():
        existing = json.loads((build / "security-master-manifest.json").read_text(encoding="utf-8"))
        if existing["output_sha256"] != output_hash or (build / "security-master.csv").read_bytes() != payload:
            raise ValueError("immutable PIT build was modified")
        return existing
    build.mkdir(parents=True)
    (build / "security-master.csv").write_bytes(payload)
    (build / "security-master-manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    (build / "snapshot-audit.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return manifest

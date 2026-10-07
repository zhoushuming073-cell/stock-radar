"""Reviewed, scoped evidence enrichment of the existing Security Master contract.

Name regexes select candidate observations only. Identity is supplied by reviewed
issuer/class/date evidence. Candidates and conflicting claims never merge IDs.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
import hashlib
import json
from pathlib import Path
import re

import pandas as pd

from radar.pit.builder import digest

STATUSES = {"verified", "strongly_supported", "inferred", "conflicting", "unresolved"}
TYPES = {"common", "adr", "etf", "etn", "preferred", "warrant", "unit", "rights",
         "spac", "closed_end_fund", "test", "other", "unknown"}
EVENTS = {"listing", "delisting", "symbol_change", "exchange_transfer", "trading_suspension",
          "merger", "bankruptcy", "split", "dividend", "equity_cancellation"}


def load_catalog(path: Path, raw: Path | None = None) -> dict:
    catalog = json.loads(path.read_text(encoding="utf-8"))
    if catalog.get("schema_version") != 1:
        raise ValueError("unsupported evidence catalog")
    sources = catalog["sources"]
    for key, source in sources.items():
        if not source.get("url", "").startswith("https://") or not source.get("source_version"):
            raise ValueError("evidence requires URL and document version")
        sha = source.get("raw_sha256", "")
        if not re.fullmatch(r"[a-f0-9]{64}", sha):
            raise ValueError("evidence requires raw content hash")
        if raw is not None:
            if hashlib.sha256((raw / (sha + ".raw")).read_bytes()).hexdigest() != sha:
                raise ValueError("evidence raw hash mismatch: " + key)
    for row in catalog["mappings"]:
        for key in ("security_id", "symbol", "old_symbol", "new_symbol", "effective_date",
                    "issuer_id", "share_class", "exchange", "valid_from", "valid_to",
                    "source", "confidence", "method", "observed_name_pattern", "security_type"):
            if key not in row or (not row[key] and key not in ("old_symbol", "new_symbol")):
                raise ValueError("identity decision missing " + key)
        if row["confidence"] not in STATUSES or row["security_type"] not in TYPES:
            raise ValueError("invalid identity/type status")
        if row["source"] not in sources:
            raise ValueError("unknown evidence source")
        if date.fromisoformat(row["valid_from"]) > date.fromisoformat(row["valid_to"]):
            raise ValueError("reversed identity scope")
    # Only verified, security-level decisions are accepted. Conflicting candidates
    # are retained separately and cannot be used as price bindings.
    verified = [r for r in catalog["mappings"] if r["confidence"] == "verified"]
    for i, a in enumerate(verified):
        for b in verified[i + 1:]:
            overlap = max(a["valid_from"], b["valid_from"]) <= min(a["valid_to"], b["valid_to"])
            if overlap and a["symbol"] == b["symbol"]:
                raise ValueError("overlapping verified symbol evidence")
            if a["security_id"] == b["security_id"]:
                if (a["issuer_id"], a["share_class"]) != (b["issuer_id"], b["share_class"]):
                    raise ValueError("issuer/class contamination")
                if overlap:
                    raise ValueError("overlapping stable identity evidence")
    for event in catalog["events"]:
        if event["event_type"] not in EVENTS or event["confidence"] not in STATUSES:
            raise ValueError("invalid event")
        date.fromisoformat(event["effective_date"])
        if event["source"] not in sources:
            raise ValueError("unknown event source")
    return catalog


def enrich(frame: pd.DataFrame, catalog: dict) -> tuple[pd.DataFrame, dict]:
    """Preserve observation fields, audit corrections, never create phantom episodes."""
    rows, decisions, conflicts = frame.to_dict("records"), [], []
    accepted = [r for r in catalog["mappings"] if r["confidence"] == "verified"]
    for row in rows:
        for key in ("valid_from", "valid_to", "listing_date", "delisting_date"):
            value = row.get(key)
            row[key] = str(pd.Timestamp(value).date()) if pd.notna(value) and str(value) else ""
        row.setdefault("observed_first", row.get("first_observed_date", row["valid_from"]))
        row.setdefault("observed_last", row.get("last_observed_date", row["valid_to"]))
        row.setdefault("classification_source", "rreichel3/US-Stock-Symbols:" + str(row.get("type_method", "unresolved")))
        row.setdefault("classification_confidence", row.get("type_resolution_status", "unresolved"))
        candidates = [m for m in accepted if m["symbol"] == row["symbol"]
                      and m["exchange"] == row["exchange"]
                      and re.search(m["observed_name_pattern"], row.get("security_name", ""), re.I)
                      and max(m["valid_from"], row["valid_from"]) <= min(m["valid_to"], row["valid_to"])]
        if len(candidates) > 1:
            raise ValueError("ambiguous official observation scope")
        if not candidates:
            continue
        mapping = candidates[0]
        source = catalog["sources"][mapping["source"]]
        old_id = row["security_id"]
        row["security_id"] = mapping["security_id"]
        row["resolution_status"] = "verified"
        row["identity_resolution_method"] = mapping["method"]
        row["identity_evidence_url"] = source["url"]
        row["identity_evidence_hash"] = source["raw_sha256"]
        row["issuer_id"], row["share_class"] = mapping["issuer_id"], mapping["share_class"]
        row["security_type"] = mapping["security_type"]
        row["eligible"] = mapping["security_type"] == "common"
        row["classification_source"] = source["url"]
        row["classification_confidence"] = "verified"
        before = (row["valid_from"], row["valid_to"])
        row["valid_from"] = max(row["valid_from"], mapping["valid_from"])
        row["valid_to"] = min(row["valid_to"], mapping["valid_to"])
        if before != (row["valid_from"], row["valid_to"]):
            conflicts.append({"security": row["security_id"], "issue_type": "observation_boundary",
                "source_a": "NASDAQ Screener Git observations", "source_b": source["url"],
                "values_a": before, "values_b": (row["valid_from"], row["valid_to"]),
                "preferred_evidence": source["url"], "reason": "verified symbol/trading boundary",
                "resolution_status": "verified"})
        decisions.append({**mapping, "old_security_id": old_id, "source_url": source["url"],
                          "source_version": source["source_version"], "evidence_hash": source["raw_sha256"]})
    result = pd.DataFrame(rows)
    # A boundary can precede the first screener observation by a few days. Extend
    # only the first covered official segment, after checking a nearby observation.
    for mapping in accepted:
        match = result.security_id.eq(mapping["security_id"]) & result.symbol.eq(mapping["symbol"]) & result.exchange.eq(mapping["exchange"])
        indices = result.index[match]
        if not len(indices) or not mapping.get("extend_first_observation"):
            continue
        index = result.loc[indices].valid_from.idxmin()
        delta = (date.fromisoformat(result.loc[index, "valid_from"]) - date.fromisoformat(mapping["valid_from"])).days
        if 0 < delta <= 4:
            conflicts.append({"security": mapping["security_id"], "issue_type": "screener_lag",
                "source_a": "NASDAQ Screener", "source_b": catalog["sources"][mapping["source"]]["url"],
                "values_a": result.loc[index, "valid_from"], "values_b": mapping["valid_from"],
                "preferred_evidence": mapping["source"], "reason": "nearby official effective date",
                "resolution_status": "verified"})
            result.loc[index, "valid_from"] = mapping["valid_from"]
    # Only actual listing/delisting events fill contract fields; suspensions and
    # merger closes stay separate. A Form 25 filing is not inferred legal effect.
    for event in catalog["events"]:
        if event["confidence"] == "verified" and event["event_type"] in ("listing", "delisting"):
            result.loc[result.security_id.eq(event["security_id"]), event["event_type"] + "_date"] = event["effective_date"]
    for key in ("classification_source", "classification_confidence"):
        if key not in result:
            result[key] = ""
    result["classification_source"] = result.classification_source.fillna("")
    result["classification_confidence"] = result.classification_confidence.fillna("")
    result = result.sort_values(["symbol", "valid_from", "security_id"], kind="stable").fillna("").reset_index(drop=True)
    return result, {"decisions": decisions, "conflicts": conflicts + catalog.get("conflicts", []),
                    "events": catalog["events"], "catalog_sha256": digest(catalog)}


def episode_candidates(frame: pd.DataFrame) -> list[dict]:
    """Classify candidates without treating a repeated name as a final merge."""
    output = []
    for symbol, group in frame.groupby("symbol", sort=True):
        if group.security_id.nunique() <= 1:
            continue
        group = group.sort_values("valid_from")
        kinds, reasons = [], []
        previous = None
        for row in group.itertuples(index=False):
            if previous is None:
                previous = row
                continue
            gap = (pd.Timestamp(row.valid_from) - pd.Timestamp(previous.valid_to)).days - 1
            verified = getattr(row, "resolution_status", "") == getattr(previous, "resolution_status", "") == "verified"
            if verified and row.security_id != previous.security_id:
                kind = "ticker_reuse"
            elif row.exchange != previous.exchange:
                kind = "exchange_transfer_candidate"
            elif row.security_type != previous.security_type:
                kind = "security_type_change_candidate"
            elif row.security_name == previous.security_name and gap > 4:
                kind = "source_gap_restore_candidate"
            elif row.security_name == previous.security_name and gap >= 0:
                kind = "short_absence_candidate"
            else:
                kind = "unknown"
            kinds.append(kind)
            reasons.append({"from_id": previous.security_id, "to_id": row.security_id,
                            "gap_calendar_days": gap, "classification": kind})
            previous = row
        output.append({"symbol": symbol, "episodes": int(group.security_id.nunique()),
                       "classes": sorted(set(kinds)), "transitions": reasons,
                       "resolution_status": "verified" if set(kinds) == {"ticker_reuse"} else "unresolved"})
    return output

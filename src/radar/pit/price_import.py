"""Offline acceptance of reviewed external bars into an identity-bound store."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from radar.pit.builder import digest
from radar.pit.features import file_hash
from radar.schema import EXPECTED_COLUMNS, ensure_research_schema


def accept_prices(raw: Path, review: dict, master, output: Path, *, raw_actions: list[dict] | None = None,
                  validate_only: bool = False) -> dict:
    """Require scope, hashes, license, adjustment proof and complete real sessions.

    Never infer an alias or a settlement. This first batch supports raw OHLCV
    without splits, making it equivalent to split-only research prices within
    these reviewed lifetimes. General factor normalization is deliberately blocked.
    """
    if output.exists() and not validate_only:
        raise ValueError("external price destination already exists")
    fields = list(EXPECTED_COLUMNS["daily_bars"]) + ["security_id"]
    payloads, evidence = [], []
    calendar = pd.DatetimeIndex(review["sessions"]).normalize()
    if calendar.has_duplicates or not calendar.is_monotonic_increasing:
        raise ValueError("review calendar must contain unique ordered real sessions")
    if file_hash(raw / review["adjustment_evidence_file"]) != review["adjustment_evidence_sha256"]:
        raise ValueError("adjustment evidence hash mismatch")
    license_sha = review["license_raw_sha256"]
    license_raw = (raw / (license_sha + ".raw")).read_bytes()
    if hashlib.sha256(license_raw).hexdigest() != license_sha:
        raise ValueError("license hash mismatch")
    license_doc = json.loads(license_raw)
    if (license_doc.get("query_execution_status") != "Success"
            or f"AS OF '{review['source_version']}'" not in license_doc.get("sql_query", "")
            or len(license_doc["rows"]) != 1
            or not license_doc["rows"][0]["doc_text"].startswith("Attribution-ShareAlike 4.0 International")):
        raise ValueError("source does not declare expected pinned license")
    for item in review["series"]:
        artifact = raw / item["file"]
        data = json.loads(artifact.read_text(encoding="utf-8"))
        if digest(data) != item["payload_sha256"]:
            raise ValueError("external raw payload hash mismatch")
        if item["confidence"] != "verified" or item["adjustment"] not in {"raw_no_splits", "raw_reviewed_actions"}:
            raise ValueError("unreviewed price basis/identity")
        if data["license"] != "CC-BY-SA-4.0" or data["provider"] != "post-no-preference/stocks":
            raise ValueError("unexpected price provider/license")
        if data["source_version"] != review["source_version"]:
            raise ValueError("price source pin mismatch")
        if not review.get("adjustment_evidence_sha256"):
            raise ValueError("price adjustment evidence required")
        captured_rows = []
        for receipt in data["queries"]:
            content = (raw / (receipt["raw_sha256"] + ".raw")).read_bytes()
            if hashlib.sha256(content).hexdigest() != receipt["raw_sha256"]:
                raise ValueError("source query hash mismatch")
            response = json.loads(content)
            if response.get("query_execution_status") != "Success" or response.get("sql_query") != receipt["sql"]:
                raise ValueError("source query failed or truncated")
            if f"AS OF '{review['source_version']}'" not in receipt["sql"]:
                raise ValueError("price query lacks immutable data pin")
            if "FROM ohlcv " in receipt["sql"]:
                captured_rows.extend(response["rows"])
            for table in ("split", "dividend", "symbol"):
                if f"FROM {table} " in receipt["sql"] and digest(response["rows"]) != digest(data["ancillary"][table]):
                    raise ValueError("ancillary data differ from raw SQL responses")
        if digest(captured_rows) != digest(data["rows"]):
            raise ValueError("aggregated prices differ from raw SQL responses")
        start, end = pd.Timestamp(item["valid_from"]), pd.Timestamp(item["valid_to"])
        for split in data["ancillary"]["split"]:
            if item['adjustment'] == 'raw_reviewed_actions' and start <= pd.Timestamp(split['ex_date']) <= end:
                candidates = [a for a in (raw_actions or []) if a['security_id'] == item['security_id']
                              and a['effective_date'] == split['ex_date'] and a['event_type'] in {'split', 'reverse_split'}
                              and a['handling_mode'] == 'native_raw_split' and a['confidence'] == 'verified']
                ratio = float(split['to_factor']) / float(split['for_factor'])
                if len(candidates) != 1 or candidates[0]['ratio'] != ratio:
                    raise ValueError('source split disagrees with reviewed official ratio/date')
            elif item['adjustment'] != 'raw_reviewed_actions' and pd.Timestamp(split["ex_date"]) >= start:
                raise ValueError("split normalization requires a separate validated factor importer")
        if item['adjustment'] == 'raw_reviewed_actions':
            if raw_actions is None:
                raise ValueError('raw price acceptance requires reviewed action ledger')
            for action in raw_actions:
                if (action['security_id'] == item['security_id'] and action['event_type'] in {'split', 'reverse_split'}
                        and start <= pd.Timestamp(action['effective_date']) <= end):
                    if not any(s['ex_date'] == action['effective_date'] for s in data['ancillary']['split']):
                        raise ValueError('official split missing from source action table')
        bars = pd.DataFrame(data["rows"]).rename(columns={"act_symbol": "symbol"})
        bars["date"] = pd.to_datetime(bars.date)
        if bars.empty or not bars.symbol.eq(item["source_symbol"]).all() or bars.date.duplicated().any():
            raise ValueError("duplicate/mismatched source prices")
        if not bars.date.between(start, end).all():
            raise ValueError("external price date outside reviewed identity interval")
        # Check the actual master, not just the review's asserted identity.
        mapped = master.filter_frame(bars).reset_index(drop=True)
        if len(mapped) != len(bars) or not mapped.security_id.eq(item["security_id"]).all():
            raise ValueError("external price identity conflicts with security master")
        mapping = master.frame[master.frame.security_id.eq(item["security_id"])]
        if not mapping.resolution_status.eq("verified").all():
            raise ValueError("external bars require verified security identity")
        for key in ("open", "high", "low", "close", "volume"):
            mapped[key] = pd.to_numeric(mapped[key], errors="raise")
        valid = (np.isfinite(mapped[["open", "high", "low", "close", "volume"]]).all(axis=1)
                 & mapped.low.gt(0) & mapped.volume.ge(0)
                 & mapped.volume.eq(np.floor(mapped.volume))
                 & mapped.open.between(mapped.low, mapped.high)
                 & mapped.close.between(mapped.low, mapped.high))
        if not valid.all():
            raise ValueError("invalid external OHLCV")
        expected = calendar[(calendar >= start) & (calendar <= end)]
        if not pd.DatetimeIndex(mapped.date).sort_values().equals(expected):
            raise ValueError("external prices missing/extra real exchange sessions")
        mapped["provider"], mapped["feed"], mapped["adjustment"] = data["provider"], "public_eod", (
            'raw' if item['adjustment'] == 'raw_reviewed_actions' else 'split')
        mapped["downloaded_at"] = pd.Timestamp(review["source_commit_time"])
        mapped["vwap"], mapped["trade_count"] = np.nan, None
        payloads.append(mapped.reindex(columns=fields))
        evidence.append({**item, "rows": len(mapped), "last_close": float(mapped.iloc[-1].close),
                         "terminal_settlement": None, "license": data["license"]})
    payload = pd.concat(payloads, ignore_index=True).sort_values(["security_id", "date"])
    if payload.duplicated(["security_id", "date"]).any() or payload.duplicated(["symbol", "date"]).any():
        raise ValueError("overlapping external price series")
    logical_sha = hashlib.sha256(payload.to_csv(index=False).encode()).hexdigest()
    if validate_only:
        return {'review_sha256':digest(review),'rows_sha256':logical_sha,'rows':len(payload)}
    output.parent.mkdir(parents=True, exist_ok=True)
    staging = output.with_suffix(".building.duckdb")
    if staging.exists():
        raise ValueError("external price staging store already exists")
    with duckdb.connect(str(staging)) as c:
        ensure_research_schema(c)
        c.execute("ALTER TABLE daily_bars ADD COLUMN security_id VARCHAR")
        c.register("accepted_payload", payload)
        c.execute("INSERT INTO daily_bars SELECT * FROM accepted_payload")
        c.execute("CHECKPOINT")
    staging.rename(output)
    manifest = {"database": str(output.resolve()), "database_sha256": file_hash(output),
                "rows_sha256": logical_sha,
                "master_output_sha256": file_hash(master.csv_path), "review_sha256": digest(review),
                "importer_sha256": file_hash(Path(__file__)), "source_version": review["source_version"],
                "series": evidence, "rows": len(payload), "status": "research_accepted_source_dependent",
                "terminal_economics": "unresolved", "license": "CC-BY-SA-4.0",
                "attribution": "post-no-preference/stocks on DoltHub; reviewed identity binding by Stock Radar",
                "limitations": ["public EOD source is not exchange-certified consolidated SIP",
                                "no general split/dividend factor normalization", "no terminal execution model"]}
    if raw_actions is not None:
        manifest['raw_actions'] = {'events_sha256':digest(raw_actions), 'events':raw_actions,
                                   'basis':'raw OHLCV; causal split-only feature transform; native raw holdings splits'}
    output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest

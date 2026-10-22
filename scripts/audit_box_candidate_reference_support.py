"""Audit dated issuer-reference support for sealed box candidates.

CIK and Nasdaq rows are historical mirror observations, not official share-
class certification. Only evidence available by each decision close is read.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import duckdb
import pandas as pd

from radar.box_labeling.history import BoxHistory
from radar.box_labeling.stage_b import digest, packed
from scripts.audit_box_candidate_execution_metadata import candidate_requests
from scripts.audit_box_candidate_issuer_at_t import build_windows
from scripts.audit_box_candidate_source_basis import audit as source_audit
from scripts.audit_box_candidate_tday_price_bridge import DOLT_SOURCE, _file_sha256
from scripts.audit_box_range_issuer_alias_at_t import (
    classify, construction_source, dated_evidence,
)

VERSION = "box-candidate-reference-support-v1"


def frozen_reference_rules(root: Path, rules_path: Path) -> tuple[dict, str, str]:
    """Bind checkout-normalized rule bytes to the frozen construction input."""
    if rules_path.name != "pit_database_rules.json":
        raise ValueError("unexpected reference rules filename")
    profile = json.loads((root / "config/research_infrastructure_v1.json")
                         .read_text(encoding="utf-8"))
    core = json.loads((root / profile["core_directory"] / "manifest.json")
                      .read_text(encoding="utf-8"))
    manifest_ref = core["inputs"]["historical_manifest"]
    manifest_path = Path(manifest_ref["path"]).resolve()
    if not manifest_path.is_relative_to(root / "data"):
        raise ValueError("historical construction manifest outside private data")
    manifest_hash = _file_sha256(manifest_path)
    if manifest_hash != manifest_ref["sha256"]:
        raise ValueError("frozen historical construction manifest drift")
    historical = json.loads(manifest_path.read_bytes())
    if historical.get("database_sha256") != core["inputs"]["historical_database"]["sha256"]:
        raise ValueError("construction manifest and database binding differ")
    expected = historical["inputs"]["rules"]["sha256"]
    normalized = rules_path.read_bytes().replace(b"\r\n", b"\n")
    if sha256(normalized).hexdigest() != expected:
        raise ValueError("reference freshness rules differ from construction input")
    rules = json.loads(normalized)
    if rules.get("policy") != "historical-database-v1":
        raise ValueError("historical reference freshness policy drift")
    return rules, expected, manifest_hash


def source_observations(connection: duckdb.DuckDBPyConnection,
                        windows: list[dict], fresh_days: int) -> list[dict]:
    if not 1 <= fresh_days <= 365:
        raise ValueError("invalid reference freshness interval")
    if not windows:
        return []
    connection.register("selected_box_support", pd.DataFrame(windows))
    rows = connection.execute("""SELECT s.task_id,
        count(DISTINCT t.interval_id) AS full_window_episodes,
        coalesce(bool_or(m.source='cik' AND m.name_compatible IS TRUE
          AND m.exchange_compatible IS TRUE AND
          datediff('day',CAST(m.available_on AS DATE),CAST(s.decision_date AS DATE))<=?),false)
          AS cik_fresh_compatible,
        coalesce(bool_or(m.source='nasdaq' AND m.name_compatible IS TRUE
          AND m.exchange_compatible IS TRUE AND
          datediff('day',CAST(m.available_on AS DATE),CAST(s.decision_date AS DATE))<=?),false)
          AS nasdaq_fresh_compatible,
        coalesce(bool_or(m.source='cik' AND m.name_compatible IS TRUE
          AND m.exchange_compatible IS TRUE),false) AS cik_ever_compatible,
        coalesce(bool_or(m.source='nasdaq' AND m.name_compatible IS TRUE
          AND m.exchange_compatible IS TRUE),false) AS nasdaq_ever_compatible,
        coalesce(bool_or((m.name_compatible IS FALSE OR
          m.exchange_compatible IS FALSE) AND
          datediff('day',CAST(m.available_on AS DATE),CAST(s.decision_date AS DATE))<=?),false)
          AS recent_reference_conflict,
        max(CAST(m.available_on AS DATE)) AS latest_available_on
      FROM selected_box_support s LEFT JOIN ticker_episode t
        ON t.security_id=s.security_id
        AND t.valid_from<=CAST(s.window_start AS DATE)
        AND t.valid_to>=CAST(s.decision_date AS DATE)
      LEFT JOIN membership_evidence m
        ON m.security_id=s.security_id AND m.interval_id=t.interval_id
        AND CAST(m.available_on AS DATE)<=CAST(s.decision_date AS DATE)
      GROUP BY s.task_id ORDER BY s.task_id""",
        [fresh_days, fresh_days, fresh_days]).fetchall()
    names = ("task_id", "full_window_episodes", "cik_fresh_compatible",
             "nasdaq_fresh_compatible", "cik_ever_compatible",
             "nasdaq_ever_compatible", "recent_reference_conflict",
             "latest_available_on")
    return [dict(zip(names, row)) for row in rows]


def support_class(row: dict) -> str:
    if row["cik_fresh_compatible"] and row["nasdaq_fresh_compatible"]:
        return "BOTH_RECENT_COMPATIBLE"
    if row["cik_fresh_compatible"]:
        return "CIK_ONLY_RECENT_COMPATIBLE"
    if row["nasdaq_fresh_compatible"]:
        return "NASDAQ_ONLY_RECENT_COMPATIBLE"
    return "NO_RECENT_COMPATIBLE_REFERENCE"


def summarize_support(issuer_rows: list[dict], support_rows: list[dict]) -> dict:
    issuers = {row["task_id"]: row for row in issuer_rows}
    supports = {row["task_id"]: row for row in support_rows}
    if (len(issuers) != len(issuer_rows) or len(supports) != len(support_rows)
            or set(issuers) != set(supports)):
        raise ValueError("issuer and reference-support task populations differ")
    cross = Counter((classify(issuers[task]), support_class(row))
                    for task, row in supports.items())
    return {
        "tasks": len(supports),
        "issuer_observation_by_reference_support": {
            category: dict(sorted((support, count)
                                  for (issuer, support), count in cross.items()
                                  if issuer == category))
            for category in sorted({key[0] for key in cross})},
        "recent_reference_conflict_tasks": sum(
            row["recent_reference_conflict"] for row in supports.values()),
        "no_full_window_ticker_episode_tasks": sum(
            row["full_window_episodes"] != 1 for row in supports.values()),
        "has_older_compatible_cik_but_not_recent": sum(
            row["cik_ever_compatible"] and not row["cik_fresh_compatible"]
            for row in supports.values()),
        "has_older_compatible_nasdaq_but_not_recent": sum(
            row["nasdaq_ever_compatible"] and not row["nasdaq_fresh_compatible"]
            for row in supports.values()),
    }


def audit(research_root: Path, split: str, start: str, end: str,
          candidate_dir: Path, detector_config: Path, context_config: Path,
          rules_path: Path) -> dict:
    root, folder = research_root.resolve(), candidate_dir.resolve()
    verified = source_audit(root, split, start, end, folder,
                            detector_config, context_config)
    expected = sum(row["candidates"] for row in verified["source_basis_counts"]
                   if row["source"] == DOLT_SOURCE and row["basis"] == "raw")
    rules, rules_hash, historical_manifest_hash = frozen_reference_rules(
        root, rules_path)
    fresh_days = rules["fresh_reference_days"]
    construction_path, construction_hash = construction_source(root)
    hashes: list[str] = []
    windows: list[dict] = []
    with BoxHistory(root) as provider:
        if provider.semantic_hash != verified["ri_semantic_hash"]:
            raise ValueError("RI semantic hash drift")
        for day_folder in sorted((folder / split).iterdir()):
            day = day_folder.name
            if not day_folder.is_dir() or not start <= day <= end:
                continue
            hashes.extend(sha256(path.read_bytes()).hexdigest()
                          for path in sorted(day_folder.glob("*.json")))
            requests = [r for r in candidate_requests(day_folder, split, day)
                        if r["source"] == DOLT_SOURCE and r["basis"] == "raw"]
            windows.extend(build_windows(provider, requests))
    if (len(windows) != expected
            or digest(packed(hashes)) != verified["verified_file_set_sha256"]):
        raise ValueError("candidate population or file set drift")
    with duckdb.connect(str(construction_path), read_only=True) as connection:
        issuer_rows = dated_evidence(connection, windows) if windows else []
        support_rows = source_observations(connection, windows, fresh_days)
    dates = {row["task_id"]: row["decision_date"] for row in windows}
    for row in support_rows:
        if (row["task_id"] not in dates or row["latest_available_on"] is not None
                and str(row["latest_available_on"]) > dates[row["task_id"]]):
            raise ValueError("reference observation after candidate decision")
    aggregate = summarize_support(issuer_rows, support_rows)
    if aggregate["tasks"] != expected:
        raise ValueError("reference support count drift")
    return {"version": VERSION, "split": split, "start": start, "end": end,
            "frozen_sessions": verified["sessions"],
            "dolt_raw_candidate_days": expected,
            "candidate_file_set_sha256": verified["verified_file_set_sha256"],
            "construction_database_sha256": construction_hash,
            "ri_semantic_hash": verified["ri_semantic_hash"],
            "reference_freshness_days": fresh_days,
            "reference_rules_sha256": rules_hash,
            "historical_manifest_sha256": historical_manifest_hash,
            "audit_source_sha256": _file_sha256(Path(__file__)),
            "source_auditor_sha256": _file_sha256(
                Path(__file__).with_name("audit_box_candidate_source_basis.py")),
            "issuer_query_sha256": _file_sha256(
                Path(__file__).with_name("audit_box_range_issuer_alias_at_t.py")),
            **aggregate,
            "official_identity_certified": False,
            "future_price_values_read": False, "future_outcomes_read": False,
            "formal_lean_ready": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--split", choices=("train", "validation"), required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--detector-config", type=Path,
                        default=Path("config/box_range_detector_stage_a_v1.yaml"))
    parser.add_argument("--context-config", type=Path,
                        default=Path("config/box_lower_band_context_v1.yaml"))
    parser.add_argument("--rules", type=Path,
                        default=Path("config/pit_database_rules.json"))
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.split, args.start, args.end,
                           args.candidate_dir, args.detector_config,
                           args.context_config, args.rules), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

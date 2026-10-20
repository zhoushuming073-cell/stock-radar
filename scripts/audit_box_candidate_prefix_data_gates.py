"""Intersect T-day price, observed issuer, and raw metadata gates by task.

This reuses frozen auditors. The ten-session horizon is a coverage diagnostic,
not a trading rule; no future OHLCV values or outcomes are read.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import duckdb

from radar.box_labeling.history import BoxHistory
from radar.box_labeling.stage_b import digest, packed
from scripts.audit_box_candidate_execution_metadata import candidate_requests
from scripts.audit_box_candidate_issuer_at_t import build_windows
from scripts.audit_box_candidate_prefix_tday import audit as prefix_tday_audit
from scripts.audit_box_candidate_tday_price_bridge import (
    DOLT_SOURCE, _file_sha256, accepted_database, compare_tday,
)
from scripts.audit_box_execution_horizon import HORIZON, horizon_metadata, summarize
from scripts.audit_box_range_issuer_alias_at_t import (
    classify, construction_source, dated_evidence,
)
from scripts.summarize_box_candidate_gates import raw_complete

VERSION = "box-candidate-prefix-data-gates-v1"


def aggregate_gates(status_by_task: dict[str, str], issuer_rows: list[dict],
                    horizon_tasks: list[dict]) -> dict:
    issuers = {row["task_id"]: row for row in issuer_rows}
    horizons = {row["task_id"]: row for row in horizon_tasks}
    if (len(issuers) != len(issuer_rows) or len(horizons) != len(horizon_tasks)
            or set(status_by_task) != set(issuers) or set(issuers) != set(horizons)):
        raise ValueError("price, issuer and horizon task populations differ")
    counts = Counter((status_by_task[task], classify(issuer),
                      raw_complete(horizons[task], HORIZON))
                     for task, issuer in issuers.items())
    return {status: {issuer_class: {
                "raw_metadata_complete": counts.get((status, issuer_class, True), 0),
                "raw_metadata_incomplete": counts.get((status, issuer_class, False), 0),
            } for issuer_class in sorted({key[1] for key in counts if key[0] == status})}
            for status in sorted(set(status_by_task.values()))}


def audit(research_root: Path, split: str, start: str, end: str,
          candidate_dir: Path, accepted_manifest: Path,
          detector_config: Path, context_config: Path) -> dict:
    root, folder = research_root.resolve(), candidate_dir.resolve()
    prior = prefix_tday_audit(root, split, start, end, folder,
                              accepted_manifest, detector_config, context_config)
    accepted_path, manifest = accepted_database(root, accepted_manifest)
    if (prior["version"] != "box-candidate-prefix-tday-v1"
            or prior["tday_only"] is not True
            or prior["accepted_database_sha256"] != manifest["database_sha256"]):
        raise ValueError("prefix T-day accepted-price contract drift")
    construction_path, construction_hash = construction_source(root)
    hashes: list[str] = []
    requests: list[dict] = []
    windows: list[dict] = []
    status_by_task: dict[str, str] = {}
    with BoxHistory(root) as provider, duckdb.connect(str(accepted_path), read_only=True) as accepted:
        if provider.semantic_hash != prior["ri_semantic_hash"]:
            raise ValueError("frozen RI semantic hash drift")
        for day_folder in sorted((folder / split).iterdir()):
            day = day_folder.name
            if not day_folder.is_dir() or not start <= day <= end:
                continue
            hashes.extend(sha256(p.read_bytes()).hexdigest()
                          for p in sorted(day_folder.glob("*.json")))
            current = [r for r in candidate_requests(day_folder, split, day)
                       if r["source"] == DOLT_SOURCE and r["basis"] == "raw"]
            requests.extend(current)
            windows.extend(build_windows(provider, current))
            for request in current:
                task = request["task_id"]
                if task in status_by_task:
                    raise ValueError("duplicate candidate task across prefix")
                status_by_task[task] = compare_tday(
                    provider.api.core.connection, accepted,
                    request["security_id"], day)
        metadata = horizon_metadata(provider.api.core.connection, requests)
        horizon_tasks, horizon_aggregate = summarize(requests, metadata)
    if (digest(packed(hashes)) != prior["candidate_file_set_sha256"]
            or dict(sorted(Counter(status_by_task.values()).items())) != prior["tday_results"]
            or len(requests) != prior["dolt_raw_candidates"]):
        raise ValueError("verified candidate file set or T-day results drift")
    with duckdb.connect(str(construction_path), read_only=True) as construction:
        issuer_rows = dated_evidence(construction, windows) if windows else []
    table = aggregate_gates(status_by_task, issuer_rows, horizon_tasks)
    return {"version": VERSION, "split": split, "start": start, "end": end,
            "frozen_sessions": prior["frozen_sessions"],
            "candidate_file_set_sha256": prior["candidate_file_set_sha256"],
            "accepted_database_sha256": manifest["database_sha256"],
            "accepted_manifest_sha256": _file_sha256(accepted_manifest),
            "construction_database_sha256": construction_hash,
            "ri_semantic_hash": prior["ri_semantic_hash"],
            "audit_source_sha256": _file_sha256(Path(__file__)),
            "tday_auditor_sha256": _file_sha256(
                Path(__file__).with_name("audit_box_candidate_prefix_tday.py")),
            "issuer_query_sha256": _file_sha256(
                Path(__file__).with_name("audit_box_range_issuer_alias_at_t.py")),
            "horizon_query_sha256": _file_sha256(
                Path(__file__).with_name("audit_box_execution_horizon.py")),
            "raw_gate_sha256": _file_sha256(
                Path(__file__).with_name("summarize_box_candidate_gates.py")),
            "dolt_raw_candidate_days": len(requests),
            "diagnostic_horizon_sessions": HORIZON,
            "horizon_aggregate": horizon_aggregate,
            "tday_price_by_issuer_observation_and_raw_metadata": table,
            "official_identity_certified": False,
            "future_price_values_read": False, "future_outcomes_read": False,
            "formal_lean_ready": False}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--research-root", type=Path, required=True)
    p.add_argument("--split", choices=("train", "validation"), required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--candidate-dir", type=Path, required=True)
    p.add_argument("--accepted-manifest", type=Path, required=True)
    p.add_argument("--detector-config", type=Path,
                   default=Path("config/box_range_detector_stage_a_v1.yaml"))
    p.add_argument("--context-config", type=Path,
                   default=Path("config/box_lower_band_context_v1.yaml"))
    a = p.parse_args()
    print(json.dumps(audit(a.research_root, a.split, a.start, a.end,
                           a.candidate_dir, a.accepted_manifest,
                           a.detector_config, a.context_config),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

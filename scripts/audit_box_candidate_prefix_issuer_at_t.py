"""Cross-tab accepted T-day prices and decision-dated issuer observations.

Reuse the frozen issuer query and candidate window contract. Neither an
observationally clear row nor a later PIT rejection certifies issuer identity.
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
from scripts.audit_box_range_issuer_alias_at_t import (
    classify, construction_source, dated_evidence,
)

VERSION = "box-candidate-prefix-issuer-asof-t-v1"


def cross_tab(rows: list[dict], status_by_task: dict[str, str]) -> dict:
    if len(rows) != len(status_by_task) or {r["task_id"] for r in rows} != set(status_by_task):
        raise ValueError("issuer observations and T-day price tasks differ")
    counts = Counter((status_by_task[row["task_id"]], classify(row)) for row in rows)
    return {status: dict(sorted((class_name, count)
                                 for (price_status, class_name), count in counts.items()
                                 if price_status == status))
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
        raise ValueError("prefix T-day price bridge drift")
    construction_path, construction_hash = construction_source(root)
    hashes: list[str] = []
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
            requests = [r for r in candidate_requests(day_folder, split, day)
                        if r["source"] == DOLT_SOURCE and r["basis"] == "raw"]
            windows.extend(build_windows(provider, requests))
            for request in requests:
                task = request["task_id"]
                if task in status_by_task:
                    raise ValueError("duplicate candidate task across prefix")
                status_by_task[task] = compare_tday(
                    provider.api.core.connection, accepted,
                    request["security_id"], day)
    if (digest(packed(hashes)) != prior["candidate_file_set_sha256"]
            or dict(sorted(Counter(status_by_task.values()).items())) != prior["tday_results"]):
        raise ValueError("verified candidate file set or T-day price results drift")
    with duckdb.connect(str(construction_path), read_only=True) as construction:
        issuer_rows = dated_evidence(construction, windows) if windows else []
    table = cross_tab(issuer_rows, status_by_task)
    return {"version": VERSION, "split": split, "start": start, "end": end,
            "frozen_sessions": prior["frozen_sessions"],
            "candidate_file_set_sha256": prior["candidate_file_set_sha256"],
            "accepted_database_sha256": manifest["database_sha256"],
            "accepted_manifest_sha256": _file_sha256(accepted_manifest),
            "construction_database_sha256": construction_hash,
            "ri_semantic_hash": prior["ri_semantic_hash"],
            "prior_auditor_sha256": _file_sha256(
                Path(__file__).with_name("audit_box_candidate_prefix_tday.py")),
            "issuer_query_sha256": _file_sha256(
                Path(__file__).with_name("audit_box_range_issuer_alias_at_t.py")),
            "candidate_window_sha256": _file_sha256(
                Path(__file__).with_name("audit_box_candidate_issuer_at_t.py")),
            "audit_source_sha256": _file_sha256(Path(__file__)),
            "dolt_raw_candidate_days": len(windows),
            "tday_price_status_by_asof_t_issuer_observation": table,
            "official_identity_certified": False,
            "future_outcomes_read": False, "human_labels_read": False,
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

"""Accepted raw record-metadata coverage after exact candidate T-day overlap.

The ten later sessions are a coverage probe, not a position holding rule.
Post-T queries select only dates, symbols and provenance, never OHLCV.
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
from scripts.audit_box_candidate_accepted_horizon import (
    HORIZON, accepted_session_metadata,
)
from scripts.audit_box_candidate_execution_metadata import candidate_requests
from scripts.audit_box_candidate_prefix_tday import audit as prefix_tday_audit
from scripts.audit_box_candidate_tday_price_bridge import (
    DOLT_SOURCE, _file_sha256, accepted_database, compare_tday,
)
from scripts.scan_box_daily_stage_d import SPLITS

VERSION = "box-candidate-prefix-horizon-metadata-v1"


def future_sessions(connection, decision_date: str, split_end: str) -> list[str]:
    return [str(row[0]) for row in connection.execute("""SELECT date
        FROM sessions WHERE date>? AND date<=? ORDER BY date LIMIT ?""",
        [decision_date, split_end, HORIZON]).fetchall()]


def audit(research_root: Path, split: str, start: str, end: str,
          candidate_dir: Path, accepted_manifest: Path,
          detector_config: Path, context_config: Path) -> dict:
    root, folder = research_root.resolve(), candidate_dir.resolve()
    prior = prefix_tday_audit(root, split, start, end, folder,
                              accepted_manifest, detector_config, context_config)
    accepted_path, manifest = accepted_database(root, accepted_manifest)
    if (prior["version"] != "box-candidate-prefix-tday-v1"
            or prior["tday_only"] is not True
            or prior["future_prices_read"] is not False
            or prior["accepted_database_sha256"] != manifest["database_sha256"]):
        raise ValueError("prefix T-day price bridge drift")
    counts: Counter[str] = Counter()
    hashes: list[str] = []
    exact = 0
    with BoxHistory(root) as provider, duckdb.connect(str(accepted_path), read_only=True) as accepted:
        if provider.semantic_hash != prior["ri_semantic_hash"]:
            raise ValueError("frozen RI semantic hash drift")
        for day_folder in sorted((folder / split).iterdir()):
            day = day_folder.name
            if not day_folder.is_dir() or not start <= day <= end:
                continue
            hashes.extend(sha256(p.read_bytes()).hexdigest()
                          for p in sorted(day_folder.glob("*.json")))
            sessions = future_sessions(provider.api.core.connection, day,
                                       SPLITS[split][1])
            for request in candidate_requests(day_folder, split, day):
                if request["source"] != DOLT_SOURCE or request["basis"] != "raw":
                    continue
                sid = request["security_id"]
                if compare_tday(provider.api.core.connection, accepted,
                                sid, day) != "exact_tday_match":
                    continue
                exact += 1
                counts["expected_sessions"] += len(sessions)
                if len(sessions) != HORIZON:
                    counts["split_censored_tasks"] += 1
                tday_symbol = accepted.execute("""SELECT symbol FROM daily_bars
                    WHERE security_id=? AND date=?""", [sid, day]).fetchone()[0]
                coverage = accepted_session_metadata(
                    accepted, sid, sessions, tday_symbol)
                counts.update(coverage)
                if len(sessions) == HORIZON and coverage.get("matching_raw", 0) == HORIZON:
                    counts["complete_metadata_tasks"] += 1
    if (digest(packed(hashes)) != prior["candidate_file_set_sha256"]
            or exact != prior["tday_results"].get("exact_tday_match", 0)):
        raise ValueError("prefix candidate set or T-day selection drift")
    return {"version": VERSION, "split": split, "start": start, "end": end,
            "frozen_sessions": prior["frozen_sessions"],
            "candidate_file_set_sha256": prior["candidate_file_set_sha256"],
            "prior_auditor_sha256": _file_sha256(
                Path(__file__).with_name("audit_box_candidate_prefix_tday.py")),
            "accepted_database_sha256": manifest["database_sha256"],
            "accepted_manifest_sha256": _file_sha256(accepted_manifest),
            "audit_source_sha256": _file_sha256(Path(__file__)),
            "ri_semantic_hash": prior["ri_semantic_hash"],
            "diagnostic_horizon_sessions": HORIZON,
            "selected_exact_tday": exact, "totals": dict(sorted(counts.items())),
            "future_price_values_read": False, "future_outcomes_read": False,
            "official_identity_certified": False,
            "corporate_actions_certified": False, "formal_lean_ready": False}


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

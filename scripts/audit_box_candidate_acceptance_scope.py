"""Explain accepted T-day absence by the older PIT closure's scope and gates.

This is a retrospective provenance diagnosis. The whole-closure risk file may
contain post-T evidence and must never become a causal candidate filter.
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
from scripts.audit_box_candidate_prefix_tday import audit as prefix_tday_audit
from scripts.audit_box_candidate_tday_price_bridge import (
    DOLT_SOURCE, _file_sha256, accepted_database, compare_tday,
)

VERSION = "box-candidate-acceptance-scope-v1"


def scope_classification(risk: dict | None) -> tuple[str, tuple[str, ...]]:
    if risk is None:
        return "outside_original_dependency", ()
    flags = tuple(name for name, failed in (
        ("whole_closure_identity_fail", not risk["research_identity_pass"]),
        ("whole_closure_material_review", risk["material_review_required"]),
        ("whole_closure_source_conflict", risk["source_price_conflict"]),
    ) if failed)
    if flags:
        return "inside_dependency_rejected_by_whole_closure_gate", flags
    return "inside_dependency_gates_passed_but_tday_not_accepted", ()


def audit(research_root: Path, split: str, start: str, end: str,
          candidate_dir: Path, accepted_manifest: Path,
          detector_config: Path, context_config: Path) -> dict:
    root, folder = research_root.resolve(), candidate_dir.resolve()
    prior = prefix_tday_audit(root, split, start, end, folder,
                              accepted_manifest, detector_config, context_config)
    accepted_path, manifest = accepted_database(root, accepted_manifest)
    risk_path = root / "data/pit/research-grade/identity-risk.json"
    if (prior["version"] != "box-candidate-prefix-tday-v1"
            or prior["tday_only"] is not True
            or prior["accepted_database_sha256"] != manifest["database_sha256"]
            or _file_sha256(risk_path) != manifest["identity_risk_sha256"]):
        raise ValueError("accepted PIT price/risk closure drift")
    risk_rows = json.loads(risk_path.read_bytes())["rows"]
    risk_by_id = {row["security_id"]: row for row in risk_rows}
    if len(risk_by_id) != len(risk_rows):
        raise ValueError("duplicate private PIT risk identity")
    results: Counter[str] = Counter()
    missing_scope: Counter[str] = Counter()
    overlaps: Counter[str] = Counter()
    identity_levels: Counter[str] = Counter()
    identity_reasons: Counter[str] = Counter()
    hashes: list[str] = []
    with BoxHistory(root) as provider, duckdb.connect(str(accepted_path), read_only=True) as accepted:
        if provider.semantic_hash != prior["ri_semantic_hash"]:
            raise ValueError("frozen RI semantic hash drift")
        for day_folder in sorted((folder / split).iterdir()):
            day = day_folder.name
            if not day_folder.is_dir() or not start <= day <= end:
                continue
            hashes.extend(sha256(p.read_bytes()).hexdigest()
                          for p in sorted(day_folder.glob("*.json")))
            for request in candidate_requests(day_folder, split, day):
                if request["source"] != DOLT_SOURCE or request["basis"] != "raw":
                    continue
                sid = request["security_id"]
                result = compare_tday(provider.api.core.connection,
                                      accepted, sid, day)
                results[result] += 1
                if result == "exact_tday_match":
                    if sid not in risk_by_id:
                        raise ValueError("accepted price outside frozen PIT risk closure")
                elif result == "accepted_tday_missing":
                    risk = risk_by_id.get(sid)
                    category, flags = scope_classification(risk)
                    missing_scope[category] += 1
                    overlaps.update(flags)
                    if risk is not None:
                        identity_levels[risk["level"]] += 1
                        identity_reasons.update(risk["reasons"])
    if (digest(packed(hashes)) != prior["candidate_file_set_sha256"]
            or dict(sorted(results.items())) != prior["tday_results"]
            or sum(missing_scope.values()) != results["accepted_tday_missing"]):
        raise ValueError("verified candidate population or T-day results drift")
    return {"version": VERSION, "split": split, "start": start, "end": end,
            "frozen_sessions": prior["frozen_sessions"],
            "candidate_file_set_sha256": prior["candidate_file_set_sha256"],
            "accepted_database_sha256": manifest["database_sha256"],
            "accepted_manifest_sha256": _file_sha256(accepted_manifest),
            "identity_risk_sha256": manifest["identity_risk_sha256"],
            "pit_dependency_sha256": manifest["dependency_sha256"],
            "prior_auditor_sha256": _file_sha256(
                Path(__file__).with_name("audit_box_candidate_prefix_tday.py")),
            "audit_source_sha256": _file_sha256(Path(__file__)),
            "ri_semantic_hash": prior["ri_semantic_hash"],
            "dolt_raw_candidates": prior["dolt_raw_candidates"],
            "tday_results": dict(sorted(results.items())),
            "accepted_missing_scope": dict(sorted(missing_scope.items())),
            "whole_closure_gate_overlaps": dict(sorted(overlaps.items())),
            "retrospective_identity_levels": dict(sorted(identity_levels.items())),
            "retrospective_identity_reasons_overlapping": dict(sorted(identity_reasons.items())),
            "risk_artifact_is_retrospective_not_tday_filter": True,
            "candidate_selection_changed": False,
            "future_price_values_read": False, "future_outcomes_read": False,
            "official_identity_certified": False,
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

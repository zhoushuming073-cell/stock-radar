"""Audit a causal necessary-condition gate against one complete daily scan.

The gate is only for retrieving Stage C `NEAR_LOWER_STABILIZING` contexts.
It cannot replace a full range-state audit or certify structure/returns.
Public output is aggregate; no security IDs or OHLCV leave local memory.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import yaml

from radar.box_labeling.fast_gate import VERSION, necessary_near_lower
from radar.box_labeling.history import BoxHistory
from radar.box_labeling.lower_band import LowerBandConfig
from scripts.scan_box_daily_stage_d import (
    dates_in_split, indexed_rows, runtime_versions, source_digest,
)
from scripts.verify_box_daily_stage_d import verify


def recent_prefixes(connection, day: str) -> list[dict]:
    """Return only T and 19 preceding source/basis-matched session values."""
    values = connection.execute("""WITH chosen AS (
        SELECT security_id,series_id,session_no,source,basis,decision_date
        FROM universe_window_index
        WHERE decision_date=? AND length=126
          AND supported_membership AND shape_research_ready
      )
      SELECT c.security_id,c.session_no,c.decision_date,count(p.date) AS n,
        count(DISTINCT p.session_no) AS distinct_sessions,
        count(DISTINCT p.date) AS distinct_dates,
        min(p.session_no) AS first_session,max(p.session_no) AS last_session,
        max(p.date) AS last_date,
        bool_and(p.source=c.source AND p.basis=c.basis
                 AND p.shape_research_ready) AS trusted,
        list(p.close ORDER BY p.session_no) AS closes,
        list(p.low ORDER BY p.session_no) AS lows,
        list(p.volume ORDER BY p.session_no) AS volumes
      FROM chosen c LEFT JOIN shape_price p
        ON p.security_id=c.security_id AND p.series_id=c.series_id
       AND p.session_no BETWEEN c.session_no-19 AND c.session_no
       AND p.date<=CAST(? AS DATE)
      GROUP BY c.security_id,c.session_no,c.decision_date ORDER BY c.security_id""",
      [day, day]).fetchall()
    names = ("security_id", "session_no", "decision_date", "n",
             "distinct_sessions", "distinct_dates", "first_session",
             "last_session", "last_date", "trusted", "closes", "lows", "volumes")
    return [dict(zip(names, row)) for row in values]


def safe_prefix(row: dict) -> bool:
    return (row["n"] == 20 and row["distinct_sessions"] == 20
            and row["distinct_dates"] == 20
            and row["first_session"] == row["session_no"]-19
            and row["last_session"] == row["session_no"]
            and row["last_date"] == row["decision_date"]
            and row["trusted"] is True)


def audit(research_root: Path, split: str, day: str, scan_output_dir: Path,
          context_config_path: Path, detector_config_path: Path) -> dict:
    config = LowerBandConfig.from_mapping(yaml.safe_load(context_config_path.read_bytes()))
    with BoxHistory(research_root) as provider:
        if dates_in_split(provider.api.core.connection, split, day, day) != [day]:
            raise ValueError("day is not a frozen Train/Validation session")
        eligible, denominator = indexed_rows(provider.api.core.connection, day)
        prefixes = recent_prefixes(provider.api.core.connection, day)
        semantic_hash = provider.semantic_hash
    eligible_ids = {r["security_id"] for r in eligible}
    if (len(prefixes) != denominator["eligible"] or
            {r["security_id"] for r in prefixes} != eligible_ids):
        raise ValueError("recent-prefix query does not cover full eligible index")
    possible_ids = set()
    unknown = 0
    rejected_reasons = Counter()
    for row in prefixes:
        if not safe_prefix(row):
            unknown += 1
            possible_ids.add(row["security_id"])
            continue
        possible, reasons = necessary_near_lower(
            row["closes"], row["lows"], row["volumes"], config)
        if possible:
            possible_ids.add(row["security_id"])
            unknown += "unknown_recent_prefix" in reasons
        else:
            rejected_reasons.update(reasons)
    verified = verify(research_root, split, day, day, scan_output_dir,
                      detector_config_path, context_config_path)
    if not verified["complete"] or verified["eligible_security_days"] != denominator["eligible"]:
        raise ValueError("full detector comparison day is incomplete")
    folder = scan_output_dir.resolve() / split / day
    near_ids = set()
    for path in sorted(folder.glob("*.json")):
        payload = json.loads(path.read_bytes())["payload"]
        for row in payload["contexts"]:
            if any(context["state"] == "NEAR_LOWER_STABILIZING"
                   for context in row["detectors"].values()):
                near_ids.add(row["security_id"])
    false_excluded = len(near_ids - possible_ids)
    if false_excluded:
        raise ValueError("necessary gate excluded a known near-lower context")
    return {"version": VERSION, "split": split, "decision_date": day,
            "ri_semantic_hash": semantic_hash,
            "audit_code_sha256": source_digest(Path(__file__)),
            "gate_code_sha256": source_digest(Path(__file__).resolve().parents[1] /
                                               "src/radar/box_labeling/fast_gate.py"),
            "gate_config_hash": config.digest,
            "runtime_versions": runtime_versions(),
            "full_scan_file_set_sha256": verified["verified_file_set_sha256"],
            "eligible_security_days": denominator["eligible"],
            "trusted_recent_prefixes": denominator["eligible"]-unknown,
            "unknown_or_untrusted_prefixes_retained": unknown,
            "possible_near_lower": len(possible_ids),
            "certainly_not_near_lower": denominator["eligible"]-len(possible_ids),
            "rejection_reasons_overlapping": dict(sorted(rejected_reasons.items())),
            "full_scan_near_lower_union": len(near_ids),
            "observed_false_exclusions": false_excluded,
            "candidate_only_prerequisite": True,
            "future_prices_read": False, "future_outcomes_read": False,
            "formal_signal_stream": False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--research-root", type=Path, required=True)
    p.add_argument("--split", choices=("train", "validation"), required=True)
    p.add_argument("--day", required=True)
    p.add_argument("--scan-output-dir", type=Path, required=True)
    p.add_argument("--context-config", type=Path,
                   default=Path("config/box_lower_band_context_v1.yaml"))
    p.add_argument("--detector-config", type=Path,
                   default=Path("config/box_range_detector_stage_a_v1.yaml"))
    a = p.parse_args()
    print(json.dumps(audit(a.research_root, a.split, a.day,
                           a.scan_output_dir, a.context_config,
                           a.detector_config), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

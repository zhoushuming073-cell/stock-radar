"""Compare a complete candidate-only receipt with a sealed full-state day.

Reads private identities only in memory; prints aggregate equality evidence.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.scan_box_near_lower_stage_d import TARGET, execute
from scripts.verify_box_daily_stage_d import verify as verify_full


def _near_rows(folder: Path, key: str, filter_target: bool) -> dict:
    found = {}
    for path in sorted(folder.glob("*.json")):
        payload = json.loads(path.read_bytes())["payload"]
        for row in payload[key]:
            detectors = {name: context for name, context in row["detectors"].items()
                         if context["state"] == TARGET} if filter_target else row["detectors"]
            if detectors:
                security_id = row["security_id"]
                if security_id in found:
                    raise ValueError("duplicate near-lower identity across chunks")
                found[security_id] = {**row, "detectors": detectors}
    return found


def compare(research_root: Path, split: str, day: str,
            candidate_dir: Path, full_dir: Path,
            detector_config: Path, context_config: Path) -> dict:
    candidate = execute(research_root, split, day, day, candidate_dir,
                        detector_config, context_config, verify_only=True)
    full = verify_full(research_root, split, day, day, full_dir,
                       detector_config, context_config)
    if not candidate["complete"] or not full["complete"]:
        raise ValueError("both reference scans must be complete")
    if candidate["eligible_security_days"] != full["eligible_security_days"]:
        raise ValueError("eligible denominators differ")
    candidate_rows = _near_rows(candidate_dir / split / day, "near_contexts", False)
    full_rows = _near_rows(full_dir / split / day, "contexts", True)
    if candidate_rows != full_rows:
        raise ValueError("candidate scan differs from sealed full-state near-lower results")
    return {"split": split, "decision_date": day,
            "eligible_security_days": candidate["eligible_security_days"],
            "gate_possible": candidate["possible_security_days"],
            "gate_certainly_not": candidate["certainly_not_security_days"],
            "candidate_near_lower": len(candidate_rows),
            "full_near_lower": len(full_rows),
            "exact_context_equality": True,
            "candidate_file_set_sha256": candidate["verified_file_set_sha256"],
            "full_file_set_sha256": full["verified_file_set_sha256"],
            "future_outcomes_read": False, "formal_signal_stream": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--split", choices=("train", "validation"), required=True)
    parser.add_argument("--day", required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--full-dir", type=Path, required=True)
    parser.add_argument("--detector-config", type=Path,
                        default=Path("config/box_range_detector_stage_a_v1.yaml"))
    parser.add_argument("--context-config", type=Path,
                        default=Path("config/box_lower_band_context_v1.yaml"))
    args = parser.parse_args()
    print(json.dumps(compare(args.research_root, args.split, args.day,
                             args.candidate_dir, args.full_dir,
                             args.detector_config, args.context_config),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

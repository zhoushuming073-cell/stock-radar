"""Aggregate provenance of sealed box candidates without exposing identities.

This read-only audit first runs the existing candidate verifier, then binds its
own aggregate to the exact verified chunk-file set. It does not read OHLCV,
future outcomes or execute trades.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

from radar.box_labeling.stage_b import digest, packed
from scripts.scan_box_daily_stage_d import SPLITS, source_digest
from scripts.scan_box_near_lower_stage_d import execute

VERSION = "box-candidate-source-basis-audit-v1"


def summarize_verified_files(folder: Path, split: str, start: str,
                             end: str, verified: dict) -> dict:
    if (verified.get("complete") is not True
            or verified.get("verify_only") is not True
            or verified.get("missing_chunks") != 0
            or verified.get("split") != split
            or verified.get("start") != start
            or verified.get("end") != end
            or not verified.get("verified_file_set_sha256")):
        raise ValueError("candidate interval is not completely verified")
    counts: Counter[tuple[str, str]] = Counter()
    hashes: list[str] = []
    files = 0
    for day_folder in sorted(folder.iterdir()) if folder.exists() else ():
        if not day_folder.is_dir() or not start <= day_folder.name <= end:
            continue
        for path in sorted(day_folder.glob("*.json")):
            raw = path.read_bytes()
            hashes.append(sha256(raw).hexdigest())
            files += 1
            for row in json.loads(raw)["payload"]["near_contexts"]:
                source, basis = row["source"], row["basis"]
                if not isinstance(source, str) or not source or basis not in ("raw", "split"):
                    raise ValueError("candidate source or basis invalid")
                counts[(source, basis)] += 1
    if (files != verified["verified_chunks"]
            or digest(packed(hashes)) != verified["verified_file_set_sha256"]
            or sum(counts.values()) != verified["near_lower_union_rows"]):
        raise ValueError("candidate file set or provenance count drift")
    return {"version": VERSION, "split": split, "start": start, "end": end,
            "sessions": verified["sessions"],
            "eligible_security_days": verified["eligible_security_days"],
            "near_lower_union_rows": verified["near_lower_union_rows"],
            "verified_chunks": files,
            "verified_file_set_sha256": verified["verified_file_set_sha256"],
            "ri_semantic_hash": verified["ri_semantic_hash"],
            "source_basis_counts": [
                {"source": source, "basis": basis, "candidates": count}
                for (source, basis), count in sorted(counts.items())],
            "future_ohlcv_values_read": False, "future_outcomes_read": False,
            "formal_lean_ready": False}


def audit(research_root: Path, split: str, start: str, end: str,
          candidate_dir: Path, detector_config: Path,
          context_config: Path) -> dict:
    if split not in ("train", "validation") or split not in SPLITS:
        raise ValueError("source audit is limited to Train/Validation")
    verified = execute(research_root, split, start, end, candidate_dir,
                       detector_config, context_config, verify_only=True)
    result = summarize_verified_files(candidate_dir.resolve() / split,
                                      split, start, end, verified)
    result["audit_source_sha256"] = source_digest(Path(__file__))
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--split", choices=("train", "validation"), required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--candidate-dir", type=Path, required=True)
    parser.add_argument("--detector-config", type=Path,
                        default=Path("config/box_range_detector_stage_a_v1.yaml"))
    parser.add_argument("--context-config", type=Path,
                        default=Path("config/box_lower_band_context_v1.yaml"))
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.split, args.start, args.end,
                           args.candidate_dir, args.detector_config,
                           args.context_config), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

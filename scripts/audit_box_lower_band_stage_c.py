"""Read-only Stage C context diagnostic on the frozen Stage B Train/Validation set.

Private per-security output stays in ignored local storage. Stdout is aggregate
coverage only; neither label databases nor future outcomes are opened.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path

import yaml

from radar.box_labeling.history import BoxHistory
from radar.box_labeling.lower_band import LowerBandConfig, assess_lower_band
from radar.box_labeling.range_detector import (
    ConfirmedPivotDetector, QuantileZoneDetector, RangeConfig,
)
from radar.box_labeling.stage_b import VERSION as SELECTION_VERSION, digest, packed


def audit(research_root: Path, selection_path: Path, expected_sha256: str,
          output_path: Path, detector_config_path: Path,
          context_config_path: Path) -> dict:
    if output_path.exists():
        raise FileExistsError("private Stage C diagnostic is immutable")
    selection_raw = selection_path.read_bytes()
    if digest(selection_raw) != expected_sha256:
        raise ValueError("frozen selection hash mismatch")
    frozen = json.loads(selection_raw)
    if (frozen.get("version") != SELECTION_VERSION
            or frozen.get("selection_precedes_detector") is not True
            or len(frozen.get("rows", [])) != 48
            or {r.get("split") for r in frozen["rows"]} - {"train", "validation"}):
        raise ValueError("Stage C needs the frozen 48 Train/Validation tasks")
    detector_config = RangeConfig.from_mapping(yaml.safe_load(detector_config_path.read_bytes()))
    context_config = LowerBandConfig.from_mapping(yaml.safe_load(context_config_path.read_bytes()))
    detectors = (QuantileZoneDetector(), ConfirmedPivotDetector())
    private = {"version": "box-lower-band-stage-c-diagnostic-v1",
               "selection_sha256": expected_sha256,
               "detector_config_hash": detector_config.digest,
               "context_config_hash": context_config.digest,
               "ri_semantic_hash": frozen["ri_semantic_hash"],
               "identity_gate": "PROVISIONAL_OBSERVATIONAL",
               "human_labels_read": False, "future_outcomes_read": False,
               "rows": []}
    with BoxHistory(research_root) as provider:
        if provider.semantic_hash != frozen["ri_semantic_hash"]:
            raise ValueError("RI v1 semantic hash drift")
        for row in frozen["rows"]:
            history = provider.history(row["security_id"], row["decision_date"], 126)
            contexts = {}
            for detector in detectors:
                scan = detector.detect(history, row["decision_date"], detector_config)
                contexts[detector.name] = asdict(assess_lower_band(
                    scan, history, detector_config, context_config))
            private["rows"].append({
                "task_id": row["task_id"], "security_id": row["security_id"],
                "decision_date": row["decision_date"], "year": row["year"],
                "split": row["split"], "contexts": contexts,
            })
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw = packed(private)
    output_path.write_bytes(raw)
    states = {detector.name: dict(sorted(Counter(
        r["contexts"][detector.name]["state"] for r in private["rows"]).items()))
        for detector in detectors}
    reasons = {detector.name: dict(sorted(Counter(reason
        for r in private["rows"]
        for reason in r["contexts"][detector.name]["reasons"]).items()))
        for detector in detectors}
    return {"version": private["version"], "selection_sha256": expected_sha256,
            "private_receipt_sha256": digest(raw), "detector_config_hash": detector_config.digest,
            "context_config_hash": context_config.digest,
            "ri_semantic_hash": frozen["ri_semantic_hash"],
            "sampled_security_days": len(private["rows"]),
            "by_year": dict(sorted(Counter(str(r["year"]) for r in private["rows"]).items())),
            "states": states, "reasons": reasons,
            "identity_gate": private["identity_gate"],
            "human_labels_read": False, "future_outcomes_read": False,
            "accuracy_or_return_claim": None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-root", required=True, type=Path)
    parser.add_argument("--selection", required=True, type=Path)
    parser.add_argument("--expected-selection-sha256", required=True)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--detector-config", type=Path,
                        default=Path("config/box_range_detector_stage_a_v1.yaml"))
    parser.add_argument("--context-config", type=Path,
                        default=Path("config/box_lower_band_context_v1.yaml"))
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.selection,
                           args.expected_selection_sha256, args.output,
                           args.detector_config, args.context_config),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

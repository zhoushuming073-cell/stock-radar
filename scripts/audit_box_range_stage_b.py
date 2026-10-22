"""Private Stage B diagnostics; no outcomes or human labels are read."""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
from hashlib import sha256
import json
from pathlib import Path

import yaml

from radar.box_labeling.history import BoxHistory
from radar.box_labeling.range_detector import (
    RangeConfig, QuantileZoneDetector, ConfirmedPivotDetector,
)
from radar.box_labeling.stage_b import digest, packed

REFERENCES = (
    ("IREN", "2025-12-26", "2026-05-15", 35.4, 59.3, 97, 86, 30.76, 65.61),
    ("RIOT", "2025-11-21", "2026-04-10", 12.5, 17.5, 95, 88, 11.50, 19.39),
    ("APLD", "2025-11-28", "2026-05-01", 23.3, 39.0, 106, 101, 20.00, 42.27),
    ("SOFI", "2026-02-27", "2026-08-07", 15.2, 19.6, 112, 111, 14.88, 20.13),
    ("IONQ", "2025-11-14", "2026-01-30", 40.9, 55.6, 52, 51, 38.00, 55.6599),
    ("POET", "2026-10-07", "2026-10-12", None, None, 4, None, 6.40, 7.60),
)


def _candidate(value):
    if value is None:
        return None
    result = asdict(value)
    # This file stays private; values are for review, not detector targets.
    return result


def _scan(history, date, config):
    result = {}
    for detector in (QuantileZoneDetector(), ConfirmedPivotDetector()):
        scan = detector.detect(history, date, config)
        result[detector.name] = {
            "input_hash": scan.input_hash,
            "status_at_t": scan.status_at_t,
            "structure_exists_in_past": scan.structure_exists_in_past,
            "active_unbroken_box_at_t": scan.active_unbroken_box_at_t,
            "evaluated_windows": scan.evaluated_windows,
            "formation_counts": scan.formation_counts,
            "rejection_counts": scan.rejection_counts,
            "best_historical": _candidate(scan.best_historical),
            "best_active": _candidate(scan.best_active),
        }
    return result


def audit(research_root: Path, selection_path: Path, output: Path,
          config_path: Path) -> dict:
    config = RangeConfig.from_mapping(yaml.safe_load(config_path.read_bytes()))
    selection_raw = selection_path.read_bytes()
    frozen = json.loads(selection_raw)
    if not frozen.get("selection_precedes_detector") or len(frozen["rows"]) != 48:
        raise ValueError("blind pool must be independently frozen first")
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        raise FileExistsError("private detector audit is immutable")
    private = {"version": "box-range-stage-b-audit-v1",
               "selection_sha256": digest(selection_raw),
               "config_sha256": config.digest,
               "detector_source_sha256": digest((Path(__file__).resolve().parents[1] /
                   "src/radar/box_labeling/range_detector.py").read_bytes().replace(b"\r\n", b"\n")),
               "reference": [], "blind": []}
    with BoxHistory(research_root) as provider:
        if provider.semantic_hash != frozen["ri_semantic_hash"]:
            raise ValueError("RI v1 semantic hash drift")
        connection = provider.api.core.connection
        for symbol, start, end, lower, upper, n, inside, low, high in REFERENCES:
            rows = connection.execute("""SELECT security_id,source,basis,
              membership_status,shape_research_ready FROM universe_window_index
              WHERE historical_ticker=? AND decision_date=? AND length=126""",
              [symbol, end]).fetchall()
            item = {"symbol": symbol, "reference_start": start, "reference_end": end,
                    "reference_alpaca_sip": {"bars": n, "inside_old_band": inside,
                        "low": low, "high": high, "old_band": [lower, upper]},
                    "ri_index_matches": len(rows)}
            if len(rows) == 1:
                security_id, source, basis, membership, ready = rows[0]
                item.update({"security_id": security_id, "source": source,
                    "basis": basis, "membership_status": membership,
                    "ri_ready": ready})
                stats = connection.execute("""SELECT count(*),min(low),max(high),
                    count(*) FILTER (WHERE close BETWEEN ? AND ?),
                    count(DISTINCT basis),count(DISTINCT source),
                    count(*) FILTER (WHERE known_split),
                    count(*) FILTER (WHERE NOT shape_research_ready)
                    FROM shape_price WHERE security_id=? AND date BETWEEN ? AND ?""",
                    [lower, upper, security_id, start, end]).fetchone()
                item["ri_window"] = dict(zip(("bars", "low", "high", "inside_old_band",
                    "basis_count", "source_count", "known_split_bars", "unsafe_bars"), stats))
                try:
                    history = provider.history(security_id, end, 126)
                    item["detectors"] = _scan(history, end, config)
                except ValueError as exc:
                    item["provider_rejection"] = str(exc)
            else:
                item["status"] = "RI v1 cannot independently assess this T"
            private["reference"].append(item)
        for row in frozen["rows"]:
            history = provider.history(row["security_id"], row["decision_date"], 126)
            private["blind"].append({"task_id": row["task_id"],
                "security_id": row["security_id"], "decision_date": row["decision_date"],
                "membership_status": row["membership_status"],
                "detectors": _scan(history, row["decision_date"], config)})
    raw = packed(private)
    output.write_bytes(raw)
    names = (QuantileZoneDetector.name, ConfirmedPivotDetector.name)
    blind_status = {name: Counter(r["detectors"][name]["status_at_t"]
                                  for r in private["blind"]) for name in names}
    disagreement = sum(r["detectors"][names[0]]["status_at_t"] !=
                       r["detectors"][names[1]]["status_at_t"] for r in private["blind"])
    return {"version": private["version"],
            "selection_sha256": private["selection_sha256"],
            "config_sha256": config.digest,
            "detector_source_sha256": private["detector_source_sha256"],
            "private_audit_sha256": digest(raw),
            "reference_cases": len(private["reference"]),
            "reference_ri_indexed": sum(r["ri_index_matches"] == 1 for r in private["reference"]),
            "reference_ri_unavailable": sum(r["ri_index_matches"] != 1 for r in private["reference"]),
            "blind_count": len(private["blind"]),
            "blind_states": {name: dict(sorted(counts.items()))
                             for name, counts in blind_status.items()},
            "blind_state_disagreements": disagreement,
            "human_labels_read": False, "future_outcomes_read": False,
            "accuracy_claim": None}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=Path("config/box_range_detector_stage_a_v1.yaml"))
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.selection, args.output, args.config),
                     sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

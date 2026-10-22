"""Read-only, aggregate Stage A detector receipt on frozen Train/Validation data.

No security IDs, dates, price rows, labels, future outcomes or candidate charts
are written or printed. The real store is opened through Research Infrastructure
v1; this is diagnostic coverage/runtime, not an accuracy or backtest result.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import yaml

from radar.box_labeling.history import BoxHistory
from radar.box_labeling.range_detector import (
    ConfirmedPivotDetector, QuantileZoneDetector, RangeConfig,
)


def source_digest(path: Path) -> str:
    """Stable across Git LF and Windows CRLF checkouts."""
    return sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()


def receipt(research_root: Path, config_path: Path, per_year: int, seed: str) -> dict:
    if not 1 <= per_year <= 128:
        raise ValueError("per_year must be 1..128")
    config_raw = config_path.read_bytes()
    config = RangeConfig.from_mapping(yaml.safe_load(config_raw))
    result = {
        "version": config.version,
        "config_hash": config.digest,
        "config_file_sha256": source_digest(config_path),
        "detector_code_sha256": source_digest(
            Path(__file__).resolve().parents[1] /
            "src/radar/box_labeling/range_detector.py"),
        "sample_policy": "fixed hash draw of supported, ready Train/Validation 126-session security-days; diagnostic, not independent accuracy",
        "seed": seed, "requested_per_year": per_year,
        "years": [2022, 2023, 2024, 2025],
        "future_outcomes_read": False,
        "private_rows_exported": False,
    }
    domain = """length=126 AND
      ((decision_date BETWEEN DATE '2022-01-01' AND DATE '2024-08-29') OR
       (decision_date BETWEEN DATE '2024-09-30' AND DATE '2025-09-08'))"""
    detectors = (QuantileZoneDetector(), ConfirmedPivotDetector())
    with BoxHistory(research_root) as provider:
        connection = provider.api.core.connection
        denominators = connection.execute(f"""
            SELECT year(decision_date) AS year, count(*) AS indexed_rows,
              count(*) FILTER (WHERE supported_membership) AS supported_rows,
              count(*) FILTER (WHERE shape_research_ready) AS ready_rows,
              count(*) FILTER (WHERE supported_membership AND shape_research_ready)
                AS eligible_rows
            FROM universe_window_index WHERE {domain}
            GROUP BY 1 ORDER BY 1""").fetchall()
        result["eligible_denominators"] = {
            str(year): {"indexed_rows": int(rows), "supported_rows": int(supported),
                        "ready_rows": int(ready), "eligible_rows": int(eligible)}
            for year, rows, supported, ready, eligible in denominators
        }
        selection = connection.execute(f"""
            SELECT security_id, decision_date, year(decision_date) AS year,
                   membership_status
            FROM universe_window_index WHERE {domain}
              AND supported_membership AND shape_research_ready
            QUALIFY row_number() OVER (
              PARTITION BY year(decision_date)
              ORDER BY hash(security_id || CAST(decision_date AS VARCHAR) || ?)
            ) <= ?
            ORDER BY year, decision_date, security_id""", [seed, per_year]).fetchall()
        result["selected_by_year"] = dict(sorted(Counter(str(row[2]) for row in selection).items()))
        result["selected_membership"] = dict(sorted(Counter(str(row[3]) for row in selection).items()))
        result["selected_security_days"] = len(selection)
        result["unique_selected_securities"] = len({row[0] for row in selection})
        result["ri_semantic_hash"] = provider.semantic_hash
        provider_exclusions = Counter()
        source_basis = Counter()
        summaries = {detector.name: {"status_at_t": Counter(), "formation_windows": Counter(),
                                     "rejections": Counter(), "historical": 0, "active": 0,
                                     "times_ms": [], "windows": 0}
                     for detector in detectors}
        disagreements = 0
        for security_id, decision_date, _, _ in selection:
            try:
                history = provider.history(security_id, decision_date,
                                           max_sessions=config.lookback_sessions)
            except ValueError as exc:
                # Count the existing data-safety rejection without exposing identity.
                provider_exclusions[type(exc).__name__ + ": " + str(exc)] += 1
                continue
            source_basis[str(history.attrs["source"]) + " / " +
                         str(history.attrs["basis"])] += 1
            states = []
            for detector in detectors:
                start = perf_counter()
                scan = detector.detect(history, decision_date, config)
                elapsed = (perf_counter()-start)*1000
                s = summaries[detector.name]
                s["status_at_t"][scan.status_at_t] += 1
                s["formation_windows"].update(scan.formation_counts)
                s["rejections"].update(scan.rejection_counts)
                s["historical"] += int(scan.structure_exists_in_past)
                s["active"] += int(scan.active_unbroken_box_at_t)
                s["times_ms"].append(elapsed)
                s["windows"] += scan.evaluated_windows
                states.append(scan.status_at_t)
            disagreements += int(states[0] != states[1])
        result["provider_exclusions"] = dict(sorted(provider_exclusions.items()))
        result["processed_source_basis"] = dict(sorted(source_basis.items()))
        result["processed_security_days"] = len(selection)-sum(provider_exclusions.values())
        result["detector_state_disagreements"] = disagreements
        result["detectors"] = {}
        for name, values in summaries.items():
            times = np.asarray(values["times_ms"], dtype=float)
            result["detectors"][name] = {
                "status_at_t": dict(sorted(values["status_at_t"].items())),
                "formation_windows": dict(sorted(values["formation_windows"].items())),
                "rejected_windows_by_reason": dict(sorted(values["rejections"].items())),
                "historical_structure_days": values["historical"],
                "active_structure_days": values["active"],
                "evaluated_windows": values["windows"],
                "runtime_ms": {"median": round(float(np.median(times)), 2),
                               "p95": round(float(np.quantile(times, .95)), 2),
                               "max": round(float(np.max(times)), 2)} if len(times) else None,
            }
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--config", type=Path,
                        default=Path("config/box_range_detector_stage_a_v1.yaml"))
    parser.add_argument("--per-year", type=int, default=24)
    parser.add_argument("--seed", default="box-range-stage-a-20261013")
    args = parser.parse_args()
    print(json.dumps(receipt(args.research_root, args.config, args.per_year, args.seed),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

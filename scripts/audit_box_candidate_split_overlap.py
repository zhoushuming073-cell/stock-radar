"""Aggregate observed security-ID reuse across sealed Train/Validation scans."""
from __future__ import annotations

from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

from radar.box_labeling.stage_b import digest, packed
from scripts.audit_box_candidate_distribution import audit_split

VERSION = "box-candidate-cross-split-observed-id-v1"


def _observed_days(folder: Path, verified: dict) -> dict[str, list[date]]:
    # The caller first checks every chunk against the accepted file-set hash.
    observed: dict[str, list[date]] = {}
    hashes: list[str] = []
    for day_folder in sorted(folder.iterdir()):
        if not day_folder.is_dir() or not verified["start"] <= day_folder.name <= verified["end"]:
            continue
        for path in sorted(day_folder.glob("*.json")):
            raw = path.read_bytes()
            hashes.append(sha256(raw).hexdigest())
            for row in json.loads(raw)["payload"]["near_contexts"]:
                observed.setdefault(row["security_id"], []).append(date.fromisoformat(day_folder.name))
    if len(hashes) != verified["verified_chunks"] or digest(packed(hashes)) != verified["verified_file_set_sha256"]:
        raise ValueError("candidate file set changed during overlap audit")
    return observed


def audit_overlap(train_folder: Path, validation_folder: Path,
                  train_verified: dict, validation_verified: dict) -> dict:
    train = audit_split(train_folder, train_verified)
    validation = audit_split(validation_folder, validation_verified)
    if train["split"] != "train" or validation["split"] != "validation":
        raise ValueError("Train and Validation receipts required in order")
    if train_verified["end"] >= validation_verified["start"]:
        raise ValueError("split dates overlap or are out of order")
    train_days = _observed_days(train_folder, train_verified)
    validation_days = _observed_days(validation_folder, validation_verified)
    shared = train_days.keys() & validation_days.keys()
    gaps = [(min(validation_days[sid]) - max(train_days[sid])).days for sid in shared]
    if any(gap <= 0 for gap in gaps):
        raise ValueError("observed candidate order invalid")
    return {
        "version": VERSION,
        "train_file_set_sha256": train["file_set_sha256"],
        "validation_file_set_sha256": validation["file_set_sha256"],
        "train_observed_ids": len(train_days),
        "validation_observed_ids": len(validation_days),
        "shared_observed_ids": len(shared),
        "train_candidate_days_on_shared_ids": sum(len(train_days[sid]) for sid in shared),
        "validation_candidate_days_on_shared_ids": sum(len(validation_days[sid]) for sid in shared),
        "shared_id_gap_calendar_days": {
            "min": min(gaps) if gaps else None,
            "median": median(gaps) if gaps else None,
            "max": max(gaps) if gaps else None,
            "at_most_31": sum(gap <= 31 for gap in gaps),
        },
        "identity_certified": False,
        "future_outcomes_read": False,
        "formal_signal_stream": False,
    }

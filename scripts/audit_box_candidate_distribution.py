"""Read-only distribution and duplicate-key audit of sealed box candidates."""
from __future__ import annotations

from collections import Counter
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from statistics import median

from radar.box_labeling.stage_b import digest, packed

VERSION = "box-candidate-distribution-audit-v1"


def audit_split(folder: Path, verified: dict) -> dict:
    if not (verified.get("complete") is True and verified.get("verify_only") is True
            and verified.get("missing_chunks") == 0):
        raise ValueError("complete read-only verifier receipt required")
    split, start, end = (verified[k] for k in ("split", "start", "end"))
    if split not in ("train", "validation"):
        raise ValueError("Train/Validation only")
    files: list[str] = []
    keys: set[tuple[str, str]] = set()
    years: Counter[str] = Counter()
    source_years: Counter[tuple[str, str, str]] = Counter()
    securities: Counter[str] = Counter()
    day_counts: list[int] = []
    for day_folder in sorted(folder.iterdir()):
        if not day_folder.is_dir() or not start <= day_folder.name <= end:
            continue
        daily = 0
        for path in sorted(day_folder.glob("*.json")):
            raw = path.read_bytes()
            files.append(sha256(raw).hexdigest())
            receipt = json.loads(raw)
            for row in receipt["payload"]["near_contexts"]:
                detector_days = {item["decision_date"] for item in row["detectors"].values()}
                if len(detector_days) != 1:
                    raise ValueError("candidate detector dates disagree")
                day = detector_days.pop()
                sid = row["security_id"]
                if (not isinstance(sid, str) or not sid or day != day_folder.name
                        or not start <= day <= end):
                    raise ValueError("invalid candidate identity/date")
                try:
                    if date.fromisoformat(day).isoformat() != day:
                        raise ValueError("noncanonical candidate date")
                except (TypeError, ValueError) as exc:
                    raise ValueError("invalid candidate date") from exc
                key = (day, sid)
                if key in keys:
                    raise ValueError("duplicate candidate security-day")
                keys.add(key)
                source, basis = row["source"], row["basis"]
                if not isinstance(source, str) or not source or basis not in ("raw", "split"):
                    raise ValueError("invalid source/basis")
                year = day[:4]
                years[year] += 1
                source_years[(year, source, basis)] += 1
                securities[sid] += 1
                daily += 1
        day_counts.append(daily)
    if (len(files) != verified["verified_chunks"]
            or digest(packed(files)) != verified["verified_file_set_sha256"]
            or len(keys) != verified["near_lower_union_rows"]
            or len(day_counts) != verified["sessions"]):
        raise ValueError("verified candidate file set drift")
    counts = sorted(securities.values(), reverse=True)
    return {
        "version": VERSION, "split": split, "sessions": len(day_counts),
        "chunks": len(files), "candidate_days": len(keys),
        "file_set_sha256": verified["verified_file_set_sha256"],
        "distinct_observed_security_ids": len(securities),
        "candidate_days_by_year": dict(sorted(years.items())),
        "candidate_days_by_year_source_basis": [
            {"year": year, "source": source, "basis": basis, "candidate_days": n}
            for (year, source, basis), n in sorted(source_years.items())],
        "top_10_security_candidate_days": sum(counts[:10]),
        "median_candidate_days_per_observed_security": median(counts) if counts else None,
        "max_candidate_days_per_observed_security": counts[0] if counts else 0,
        "zero_candidate_sessions": day_counts.count(0),
        "duplicate_candidate_keys": 0,
        "future_outcomes_read": False, "formal_signal_stream": False,
    }

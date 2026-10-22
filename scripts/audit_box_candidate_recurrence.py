"""Read-only observed-ID recurrence audit of sealed box candidate days."""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path

from scripts.audit_box_candidate_distribution import audit_split
from scripts.audit_box_candidate_split_overlap import _observed_days

VERSION = "box-candidate-recurrence-v1"
COOLDOWNS = (20, 60, 126)


def episode_summary(observed: dict[str, list[date]], sessions: list[date],
                    cooldown: int) -> dict[str, int]:
    if cooldown < 1 or sessions != sorted(set(sessions)):
        raise ValueError("invalid complete session calendar or cooldown")
    index = {day: i for i, day in enumerate(sessions)}
    episodes = 0
    repeated_days = 0
    largest = 0
    for dates in observed.values():
        ordered = sorted(dates)
        if len(ordered) != len(set(ordered)) or any(day not in index for day in ordered):
            raise ValueError("duplicate or out-of-calendar candidate day")
        length = 0
        previous = None
        for day in ordered:
            if previous is not None and index[day] - index[previous] > cooldown:
                episodes += 1
                repeated_days += length if length > 1 else 0
                largest = max(largest, length)
                length = 0
            length += 1
            previous = day
        if length:
            episodes += 1
            repeated_days += length if length > 1 else 0
            largest = max(largest, length)
    return {"episodes": episodes, "candidate_days_in_multi_day_episodes": repeated_days,
            "largest_episode_candidate_days": largest}


def audit_recurrence(folder: Path, verified: dict) -> dict:
    checked = audit_split(folder, verified)
    dates = sorted(date.fromisoformat(path.name) for path in folder.iterdir()
                   if path.is_dir() and verified["start"] <= path.name <= verified["end"])
    if len(dates) != verified["sessions"] or len(dates) != len(set(dates)):
        raise ValueError("candidate session calendar changed")
    observed = _observed_days(folder, verified)  # Rehash during the second read.
    if len(observed) != checked["distinct_observed_security_ids"] or sum(
            map(len, observed.values())) != checked["candidate_days"]:
        raise ValueError("candidate rows changed during recurrence audit")
    return {
        "version": VERSION, "split": checked["split"],
        "file_set_sha256": checked["file_set_sha256"],
        "sessions": len(dates), "candidate_days": checked["candidate_days"],
        "observed_ids": len(observed),
        "by_cooldown_sessions": {str(k): episode_summary(observed, dates, k)
                                 for k in COOLDOWNS},
        "cross_split_episodes_measured": False,
        "independent_input_windows_proven": False,
        "identity_certified": False, "future_outcomes_read": False,
        "formal_signal_stream": False,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    private = args.research_root / "data" / "box-range-stage-d"
    candidate = private / "near-lower-candidate-v1"
    result = {split: audit_recurrence(candidate / split, json.loads(
        (private / f"full-{split}-verify.json").read_text(encoding="utf-8")))
        for split in ("train", "validation")}
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()

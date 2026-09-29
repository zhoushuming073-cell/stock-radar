"""Versioned, immutable research split dates.

The SPY session calendar may grow. Existing research dates must not move when
new sessions arrive; only ``fresh_oos`` can grow after the frozen Test period.
"""

from __future__ import annotations

import pandas as pd


def resolve_split_windows(sessions: pd.DatetimeIndex, config: dict) -> dict:
    sessions = pd.DatetimeIndex(sessions).normalize()
    if sessions.empty or not sessions.is_monotonic_increasing or sessions.has_duplicates:
        raise ValueError("SPY sessions must be nonempty, ordered, and unique")
    embargo = int(config["embargo_sessions"])
    if embargo < int(config["max_forward_sessions"]):
        raise ValueError("embargo must cover the longest forward label")
    frozen = config.get("frozen_splits")
    if frozen is None:
        # Synthetic fixtures may deliberately use a short calendar. Production
        # research.yaml has dated boundaries and cannot silently fall back.
        if not config.get("allow_fractional_fixture_splits", False):
            raise ValueError("versioned frozen_splits are required")
        n = len(sessions)
        train_end = int(n * config["train_fraction"])
        validation_end = int(n * (config["train_fraction"] +
                                  config["validation_fraction"]))
        if (train_end <= embargo or validation_end - train_end <= 2 * embargo or
                validation_end + embargo >= n):
            raise ValueError("not enough sessions for fixture split")
        windows = {
            "train": (sessions[0], sessions[train_end - embargo - 1],
                      sessions[train_end - 1]),
            "validation": (sessions[train_end + embargo],
                           sessions[validation_end - embargo - 1],
                           sessions[validation_end - 1]),
            "test": (sessions[validation_end], sessions[n - embargo - 1],
                     sessions[-1]),
        }
    else:
        if config.get("split_version") != "research-splits-v1":
            raise ValueError("unknown frozen research split version")
        if not isinstance(frozen, dict):
            raise ValueError("frozen_splits must be a mapping")
        windows = {}
        for name in ("train", "validation", "test"):
            dates = frozen.get(name)
            if not isinstance(dates, list) or len(dates) != 3:
                raise ValueError(f"frozen {name} requires three dates")
            window = tuple(pd.Timestamp(day).normalize() for day in dates)
            if any(day not in sessions for day in window):
                raise ValueError(f"frozen {name} boundary is missing from SPY sessions")
            if not window[0] <= window[1] < window[2]:
                raise ValueError(f"frozen {name} boundaries are out of order")
            if sessions.get_loc(window[2]) - sessions.get_loc(window[1]) < embargo:
                raise ValueError(f"frozen {name} lacks its evaluation embargo")
            windows[name] = window
        train, validation, test = (windows[name] for name in
                                   ("train", "validation", "test"))
        if not (train[2] < validation[0] <= validation[1] < validation[2] <
                test[0] <= test[1] < test[2]):
            raise ValueError("frozen research splits overlap or are out of order")
        if pd.Timestamp(frozen.get("fresh_oos_after")).normalize() != test[2]:
            raise ValueError("fresh OOS must begin after frozen Test evaluation end")
    result = {"sessions": list(sessions), **windows,
              "test_start": windows["test"][0],
              "split_version": config.get("split_version", "fixture_fractional")}
    later = sessions[sessions > windows["test"][2]]
    if len(later) > embargo:
        result["fresh_oos"] = (later[0], later[-embargo - 1], later[-1])
    return result

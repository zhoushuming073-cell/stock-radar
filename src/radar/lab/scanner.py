"""Host-only forward outcomes and candidate-selection research metrics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

import numpy as np
import pandas as pd


LABEL_VERSION = "scanner-forward-v2"
DEFAULT_EVALUATION = {
    "entry_reference": "next_session_open",
    "horizon_sessions": 10,
    "upside_targets": [0.03, 0.05, 0.08, 0.10],
    "downside_targets": [-0.03, -0.05, -0.08, -0.10],
    "primary_target": 0.05,
    "top_k_values": [5, 10, 20],
    "success_rule": "target_touch",
    "event_cooldown_sessions": 5,
    "false_falling_knife": {"enabled": True, "max_drawdown_threshold": -0.08},
}


def evaluation_settings(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    value = {**DEFAULT_EVALUATION, **dict(raw or {})}
    if set(value) - set(DEFAULT_EVALUATION):
        raise ValueError(f"unknown evaluation fields: {sorted(set(value) - set(DEFAULT_EVALUATION))}")
    if value["entry_reference"] != "next_session_open":
        raise ValueError("scanner supports next_session_open only")
    horizon = value["horizon_sessions"]
    if isinstance(horizon, bool) or not isinstance(horizon, int) or not 1 <= horizon <= 60:
        raise ValueError("horizon_sessions must be an integer from 1 to 60")
    targets = value["upside_targets"]
    if (not isinstance(targets, list) or not targets or
            any(isinstance(x, bool) or not isinstance(x, (int, float)) or
                not math.isfinite(x) or not 0 < x < 1 for x in targets) or
            len(set(targets)) != len(targets)):
        raise ValueError("upside_targets must be unique positive fractions below 1")
    downs = value["downside_targets"]
    if (not isinstance(downs, list) or not downs or
            any(isinstance(x, bool) or not isinstance(x, (int, float)) or
                not math.isfinite(x) or not -1 < x < 0 for x in downs) or
            len(set(downs)) != len(downs)):
        raise ValueError("downside_targets must be unique negative fractions above -1")
    primary = value["primary_target"]
    if primary not in targets:
        raise ValueError("primary_target must be an upside target")
    top_k = value["top_k_values"]
    if (not isinstance(top_k, list) or not top_k or
            any(isinstance(x, bool) or not isinstance(x, int) or not 1 <= x <= 1000
                for x in top_k) or len(set(top_k)) != len(top_k)):
        raise ValueError("top_k_values must be unique positive integers")
    if value["success_rule"] not in {"target_touch", "target_before_adverse"}:
        raise ValueError("unknown success_rule")
    cooldown = value["event_cooldown_sessions"]
    if isinstance(cooldown, bool) or not isinstance(cooldown, int) or not 0 <= cooldown <= 60:
        raise ValueError("event_cooldown_sessions must be an integer from 0 to 60")
    knife = value["false_falling_knife"]
    if not isinstance(knife, Mapping) or not isinstance(knife.get("enabled"), bool):
        raise ValueError("false_falling_knife requires enabled boolean")
    threshold = knife.get("max_drawdown_threshold")
    if (isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or
            not math.isfinite(threshold) or not -1 < threshold < 0):
        raise ValueError("max_drawdown_threshold must be between -1 and 0")
    value["false_falling_knife"] = dict(knife)
    value["upside_targets"] = sorted(float(x) for x in targets)
    value["downside_targets"] = sorted((float(x) for x in downs), reverse=True)
    value["top_k_values"] = sorted(top_k)
    return value


def target_name(target: float, horizon: int) -> str:
    return f"hit_{_percent_token(target)}pct_{horizon}d"


def _percent_token(target: float) -> str:
    return f"{target * 100:g}".replace(".", "p")


def downside_name(target: float, horizon: int) -> str:
    return f"hit_minus_{_percent_token(abs(target))}pct_{horizon}d"


def before_adverse_name(upside: float, downside: float, horizon: int) -> str:
    return (f"up_{_percent_token(upside)}pct_before_down_"
            f"{_percent_token(abs(downside))}pct_{horizon}d")


def label_candidate(signal_date: pd.Timestamp, signal_low: float,
                    future: pd.DataFrame, settings: Mapping[str, Any]) -> dict[str, Any] | None:
    """Label a full calendar-session horizon; missing symbol bars stay unlabeled."""
    horizon = int(settings["horizon_sessions"])
    if len(future) != horizon:
        return None
    return _label_values(signal_low, future[["open", "high", "low"]].to_numpy(dtype=float), settings)


def _label_values(signal_low: float, columns: np.ndarray,
                  settings: Mapping[str, Any]) -> dict[str, Any] | None:
    horizon = int(settings["horizon_sessions"])
    if len(columns) != horizon or not math.isfinite(float(signal_low)):
        return None
    if not np.isfinite(columns).all() or (columns <= 0).any():
        return None
    entry = float(columns[0, 0])
    highs, lows = columns[:, 1], columns[:, 2]
    mfe = float(highs.max() / entry - 1)
    mae = float(lows.min() / entry - 1)
    new_low = bool((lows < float(signal_low)).any())
    knife = settings["false_falling_knife"]
    output: dict[str, Any] = {
        "entry_reference_price": entry,
        f"mfe_{horizon}": mfe,
        f"mae_{horizon}": mae,
        "new_low_after_signal": new_low,
        "false_falling_knife": bool(new_low and mae <= knife["max_drawdown_threshold"])
        if knife["enabled"] else None,
    }
    for target in settings["upside_targets"]:
        reached = np.flatnonzero(highs >= entry * (1 + target))
        output[target_name(target, horizon)] = bool(len(reached))
        output[f"time_to_{_percent_token(target)}pct"] = int(reached[0] + 1) if len(reached) else None
    ambiguous = False
    for downside in settings["downside_targets"]:
        reached = np.flatnonzero(lows <= entry * (1 + downside))
        output[downside_name(downside, horizon)] = bool(len(reached))
        output[f"time_to_minus_{_percent_token(abs(downside))}pct"] = (
            int(reached[0] + 1) if len(reached) else None)
        for upside in settings["upside_targets"]:
            up = np.flatnonzero(highs >= entry * (1 + upside))
            if len(up) and len(reached) and up[0] == reached[0]:
                outcome = None
                ambiguous = True
            else:
                outcome = bool(len(up) and (not len(reached) or up[0] < reached[0]))
            output[before_adverse_name(upside, downside, horizon)] = outcome
    output["ambiguous_same_session"] = ambiguous
    return output


def signal_event_flags(candidates: pd.DataFrame, cooldown: int,
                       sessions: Sequence[pd.Timestamp] | None = None) -> list[bool]:
    """Preserve raw observations while identifying independent symbol events."""
    if candidates.empty:
        return []
    if "symbol" not in candidates or "signal_date" not in candidates:
        return [True] * len(candidates)
    dates = (pd.DatetimeIndex(sessions) if sessions is not None
             else pd.DatetimeIndex(sorted(pd.to_datetime(candidates["signal_date"]).unique())))
    indices = {pd.Timestamp(day).normalize(): i for i, day in enumerate(dates)}
    ordered = candidates.reset_index(drop=True).copy()
    ordered["_position"] = range(len(ordered))
    ordered = ordered.sort_values(["signal_date", "symbol", "_position"])
    last: dict[str, int] = {}
    flags = [False] * len(candidates)
    for _, row in ordered.iterrows():
        index = indices.get(pd.Timestamp(row["signal_date"]).normalize())
        if index is None:
            raise ValueError("signal date absent from trading sessions")
        previous = last.get(str(row["symbol"]))
        event = previous is None or index - previous >= max(1, cooldown)
        flags[int(row["_position"])] = event
        if event:
            last[str(row["symbol"])] = index
    return flags


def build_labels(signal_rows: pd.DataFrame, bars: pd.DataFrame,
                 sessions: Sequence[pd.Timestamp],
                 settings: Mapping[str, Any]) -> pd.DataFrame:
    """Compute labels after selection from host bars, never from plugin context."""
    session_index = {pd.Timestamp(day).normalize(): i for i, day in enumerate(sessions)}
    by_symbol: dict[str, np.ndarray] = {}
    for symbol, group in bars.groupby("symbol", sort=False):
        array = np.full((len(sessions), 3), np.nan, dtype=float)
        for row in group.itertuples(index=False):
            position = session_index.get(pd.Timestamp(row.date).normalize())
            if position is not None:
                array[position] = [row.open, row.high, row.low]
        by_symbol[symbol] = array
    horizon = int(settings["horizon_sessions"])
    labels = []
    for row in signal_rows.itertuples(index=False):
        day = pd.Timestamp(row.signal_date).normalize()
        position = session_index.get(day)
        symbol_bars = by_symbol.get(row.symbol)
        result = None
        if position is not None and position + horizon < len(sessions) and symbol_bars is not None:
            result = _label_values(float(symbol_bars[position, 2]),
                                   symbol_bars[position + 1:position + horizon + 1], settings)
        labels.append(result)
    return pd.DataFrame({"label": labels})


def candidate_metrics(candidates: pd.DataFrame, background: pd.DataFrame,
                      settings: Mapping[str, Any],
                      sessions: Sequence[pd.Timestamp] | None = None) -> dict[str, Any]:
    """Top-K is evaluated per signal day against same-day eligible market rows."""
    horizon = settings["horizon_sessions"]
    target = settings["primary_target"]
    hit = target_name(target, horizon)
    outcome = hit
    if settings["success_rule"] == "target_before_adverse":
        downside = min(settings["downside_targets"], key=lambda x: abs(x + target))
        outcome = before_adverse_name(target, downside, horizon)
    labeled_base = background[background["label"].notna()].copy()
    labeled_candidates = candidates[candidates["label"].notna()].copy()
    base_values = [row.get(outcome) for row in labeled_base["label"]]
    base_values = [value for value in base_values if value is not None]
    base_rate = float(np.mean(base_values)) if base_values else None
    flags = signal_event_flags(candidates, settings["event_cooldown_sessions"], sessions)
    metrics: dict[str, Any] = {
        "candidate_count": int(len(candidates)),
        "candidate_observation_count": int(len(candidates)),
        "unique_signal_event_count": int(sum(flags)),
        "labeled_candidate_count": int(len(labeled_candidates)),
        "background_count": int(len(labeled_base)),
        "primary_target": hit,
        "primary_outcome": outcome,
        "success_rule": settings["success_rule"],
        "base_rate": base_rate,
        "label_version": LABEL_VERSION,
    }
    for k in settings["top_k_values"]:
        top = labeled_candidates[labeled_candidates["rank"] <= k]
        valid = top[top["label"].map(lambda row: row.get(outcome) is not None)]
        precision = float(np.mean([row[outcome] for row in valid["label"]])) if len(valid) else None
        metrics[f"precision_at_{k}"] = precision
        metrics[f"pooled_precision_at_{k}"] = precision
        metrics[f"lift_at_{k}"] = precision / base_rate if precision is not None and base_rate else None
        metrics[f"top_{k}_count"] = int(len(valid))
        if "signal_date" in valid:
            daily = [float(np.mean([row[outcome] for row in group["label"]]))
                     for _, group in valid.groupby("signal_date")]
        else:
            daily = []
        metrics[f"mean_daily_precision_at_{k}"] = float(np.mean(daily)) if daily else None
        metrics[f"median_daily_precision_at_{k}"] = float(np.median(daily)) if daily else None
    for name in (f"mfe_{horizon}", f"mae_{horizon}"):
        values = [row[name] for row in labeled_candidates["label"]]
        metrics[f"average_{name}"] = float(np.mean(values)) if values else None
        metrics[f"median_{name}"] = float(np.median(values)) if values else None
    knife = [row["false_falling_knife"] for row in labeled_candidates["label"]
             if row["false_falling_knife"] is not None]
    metrics["false_falling_knife_rate"] = float(np.mean(knife)) if knife else None
    for threshold in settings["upside_targets"]:
        name = target_name(threshold, horizon)
        values = [row[name] for row in labeled_candidates["label"]]
        metrics[f"{name}_rate"] = float(np.mean(values)) if values else None
        probability = f"p_{name}"
        if probability in labeled_candidates:
            calibrated = labeled_candidates[labeled_candidates[probability].notna()]
            if len(calibrated):
                predicted = calibrated[probability].to_numpy(dtype=float)
                observed = np.array([float(row[name]) for row in calibrated["label"]])
                metrics[f"{probability}_brier"] = float(np.mean((predicted - observed) ** 2))
                clipped = np.clip(predicted, 1e-12, 1 - 1e-12)
                metrics[f"{probability}_log_loss"] = float(np.mean(
                    -observed * np.log(clipped) - (1 - observed) * np.log(1 - clipped)))
                bins = []
                for low in np.arange(0, 1, 0.2):
                    mask = (predicted >= low) & (predicted < low + 0.2 if low < 0.8
                                                  else predicted <= 1)
                    if mask.any():
                        bins.append({"low": float(low), "high": float(low + 0.2),
                                     "count": int(mask.sum()),
                                     "predicted": float(predicted[mask].mean()),
                                     "observed": float(observed[mask].mean())})
                metrics[f"{probability}_calibration_bins"] = bins
    return metrics

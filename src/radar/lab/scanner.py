"""Host-only forward outcomes and candidate-selection research metrics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

import numpy as np
import pandas as pd


LABEL_VERSION = "scanner-forward-v1"
DEFAULT_EVALUATION = {
    "entry_reference": "next_session_open",
    "horizon_sessions": 10,
    "upside_targets": [0.03, 0.05, 0.08, 0.10],
    "false_falling_knife": {"enabled": True, "max_drawdown_threshold": -0.08},
}


def evaluation_settings(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    value = {**DEFAULT_EVALUATION, **dict(raw or {})}
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
    knife = value["false_falling_knife"]
    if not isinstance(knife, Mapping) or not isinstance(knife.get("enabled"), bool):
        raise ValueError("false_falling_knife requires enabled boolean")
    threshold = knife.get("max_drawdown_threshold")
    if (isinstance(threshold, bool) or not isinstance(threshold, (int, float)) or
            not math.isfinite(threshold) or not -1 < threshold < 0):
        raise ValueError("max_drawdown_threshold must be between -1 and 0")
    value["false_falling_knife"] = dict(knife)
    value["upside_targets"] = sorted(float(x) for x in targets)
    return value


def target_name(target: float, horizon: int) -> str:
    return f"hit_{_percent_token(target)}pct_{horizon}d"


def _percent_token(target: float) -> str:
    return f"{target * 100:g}".replace(".", "p")


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
    return output


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
                      settings: Mapping[str, Any]) -> dict[str, Any]:
    """Top-K is evaluated per signal day against same-day eligible market rows."""
    horizon = settings["horizon_sessions"]
    target = min(settings["upside_targets"], key=lambda x: abs(x - 0.05))
    hit = target_name(target, horizon)
    labeled_base = background[background["label"].notna()].copy()
    labeled_candidates = candidates[candidates["label"].notna()].copy()
    base_rate = (float(np.mean([row[hit] for row in labeled_base["label"]]))
                 if len(labeled_base) else None)
    metrics: dict[str, Any] = {
        "candidate_count": int(len(candidates)),
        "labeled_candidate_count": int(len(labeled_candidates)),
        "background_count": int(len(labeled_base)),
        "primary_target": hit,
        "base_rate": base_rate,
        "label_version": LABEL_VERSION,
    }
    for k in (5, 10, 20):
        top = labeled_candidates[labeled_candidates["rank"] <= k]
        precision = float(np.mean([row[hit] for row in top["label"]])) if len(top) else None
        metrics[f"precision_at_{k}"] = precision
        metrics[f"lift_at_{k}"] = precision / base_rate if precision is not None and base_rate else None
        metrics[f"top_{k}_count"] = int(len(top))
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

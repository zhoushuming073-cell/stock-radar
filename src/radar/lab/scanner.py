"""Host-only forward outcomes and candidate-selection research metrics."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
import math
from typing import Any

import numpy as np
import pandas as pd

from radar.lab.terminal import TerminalEventProvider, TERMINAL_LABEL_VERSION


LABEL_VERSION = "scanner-forward-v2"
DEFAULT_EVALUATION = {
    "entry_reference": "next_session_open",
    "horizon_sessions": 10,
    "upside_targets": [0.03, 0.05, 0.08, 0.10],
    "downside_targets": [-0.03, -0.05, -0.08, -0.10],
    "primary_target": 0.05,
    "primary_adverse_target": -0.05,
    "top_k_values": [5, 10, 20],
    "success_rule": "target_touch",
    "event_cooldown_sessions": 5,
    "false_falling_knife": {"enabled": True, "max_drawdown_threshold": -0.08},
}


def evaluation_settings(raw: Mapping[str, Any] | None) -> dict[str, Any]:
    value = {**DEFAULT_EVALUATION, **dict(raw or {})}
    if isinstance(value.get("false_falling_knife"), Mapping):
        value["false_falling_knife"] = {
            **DEFAULT_EVALUATION["false_falling_knife"],
            **value["false_falling_knife"],
        }
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
    if (isinstance(primary, bool) or not isinstance(primary, (int, float)) or
            not math.isfinite(primary) or primary not in targets):
        raise ValueError("primary_target must be an upside target")
    adverse = value["primary_adverse_target"]
    if (isinstance(adverse, bool) or not isinstance(adverse, (int, float)) or
            not math.isfinite(adverse) or adverse >= 0 or adverse not in downs):
        raise ValueError("primary_adverse_target must be a negative downside target")
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


def primary_outcome_name(settings: Mapping[str, Any]) -> str:
    if settings["success_rule"] == "target_before_adverse":
        return before_adverse_name(settings["primary_target"],
                                   settings["primary_adverse_target"],
                                   settings["horizon_sessions"])
    return target_name(settings["primary_target"], settings["horizon_sessions"])


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


def _primary_label_values(columns: np.ndarray, settings: Mapping[str, Any]) -> bool | None:
    """The base-rate universe needs only the primary outcome, not every excursion."""
    entry = float(columns[0, 0])
    highs, lows = columns[:, 1], columns[:, 2]
    upside = np.flatnonzero(highs >= entry * (1 + settings["primary_target"]))
    if settings["success_rule"] == "target_touch":
        outcome = bool(len(upside))
    else:
        downside = np.flatnonzero(lows <= entry * (1 + settings["primary_adverse_target"]))
        if len(upside) and len(downside) and upside[0] == downside[0]:
            outcome = None
        else:
            outcome = bool(len(upside) and (not len(downside) or upside[0] < downside[0]))
    return outcome


def _terminal_cash_label(observed: np.ndarray, cash: float,
                         settings: Mapping[str, Any], *, primary_only: bool) -> dict[str, Any] | bool | None:
    """Observed OHLC plus a source-attested cash payment, never an invented bar."""
    if not len(observed) or not np.isfinite(observed).all() or (observed <= 0).any():
        return None
    entry = float(observed[0, 0])
    highs, lows = observed[:, 1], observed[:, 2]
    result: dict[str, Any] = {"entry_reference_price": entry,
                              "terminal_cash_per_share": cash,
                              "terminal_return": cash / entry - 1,
                              "terminal_policy": "terminal-cash-v1"}
    ups: dict[float, int | None] = {}
    downs: dict[float, int | None] = {}
    for target in settings["upside_targets"]:
        hits = np.flatnonzero(highs >= entry * (1 + target))
        ups[target] = int(hits[0]) if len(hits) else len(observed) if cash >= entry * (1 + target) else None
        result[target_name(target, settings["horizon_sessions"])] = ups[target] is not None
    for target in settings["downside_targets"]:
        hits = np.flatnonzero(lows <= entry * (1 + target))
        downs[target] = int(hits[0]) if len(hits) else len(observed) if cash <= entry * (1 + target) else None
        result[downside_name(target, settings["horizon_sessions"])] = downs[target] is not None
    for upside, up in ups.items():
        for downside, down in downs.items():
            key = before_adverse_name(upside, downside, settings["horizon_sessions"])
            result[key] = (None if up is not None and up == down and up < len(observed)
                           else bool(up is not None and (down is None or up < down)))
    primary = primary_outcome_name(settings)
    if result[primary] is None:
        return None
    return bool(result[primary]) if primary_only else result


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
        identity = row.get("security_id") if "security_id" in ordered else None
        key = str(identity) if pd.notna(identity) else str(row["symbol"])
        previous = last.get(key)
        event = previous is None or index - previous >= max(1, cooldown)
        flags[int(row["_position"])] = event
        if event:
            last[key] = index
    return flags


def build_labels(signal_rows: pd.DataFrame, bars: pd.DataFrame,
                 sessions: Sequence[pd.Timestamp],
                 settings: Mapping[str, Any],
                 security_end_dates: Mapping[str, pd.Timestamp] | None = None,
                 *, primary_only: bool = False,
                 terminal_provider: TerminalEventProvider | None = None) -> pd.DataFrame:
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
    outcome = primary_outcome_name(settings)
    labels, statuses, reasons = [], [], []
    for row in signal_rows.itertuples(index=False):
        day = pd.Timestamp(row.signal_date).normalize()
        position = session_index.get(day)
        symbol_bars = by_symbol.get(row.symbol)
        result, reason = None, None
        if position is None or position + horizon >= len(sessions):
            reason = "insufficient_future_sessions"
        elif symbol_bars is None:
            reason = "missing_symbol_bar"
        else:
            future = symbol_bars[position + 1:position + horizon + 1]
            missing = np.isnan(future).all(axis=1)
            if missing.any():
                first_missing = int(np.flatnonzero(missing)[0])
                missing_day = pd.Timestamp(sessions[position + 1 + first_missing]).normalize()
                known_end = (security_end_dates or {}).get(str(row.symbol))
                event = (terminal_provider.event_between(str(row.symbol),
                         pd.Timestamp(sessions[position + first_missing]).normalize() +
                         pd.Timedelta(days=1), missing_day)
                         if terminal_provider is not None else None)
                if event is not None:
                    if event.settlement is None:
                        reason = "terminal_event_without_valued_outcome"
                    else:
                        result = _terminal_cash_label(future[:first_missing], event.settlement,
                                                      settings, primary_only=primary_only)
                        if result is None:
                            reason = "missing_price_data" if first_missing == 0 else "ambiguous_same_session"
                else:
                    reason = ("security_no_longer_eligible" if known_end is not None and
                              missing_day > pd.Timestamp(known_end).normalize()
                              else "missing_symbol_bar")
            elif (not np.isfinite(future).all() or (future <= 0).any() or
                  not math.isfinite(float(symbol_bars[position, 2])) or
                  symbol_bars[position, 2] <= 0):
                reason = "missing_price_data"
            else:
                result = (_primary_label_values(future, settings) if primary_only else
                          _label_values(float(symbol_bars[position, 2]), future, settings))
                if result is None:
                    reason = "ambiguous_same_session" if primary_only else "missing_price_data"
                elif not primary_only and result.get(outcome) is None:
                    reason = "ambiguous_same_session"
        labels.append(result)
        statuses.append("censored" if reason else "labeled")
        reasons.append(reason)
    return pd.DataFrame({"label": pd.Series(labels, dtype=object),
                         "label_status": statuses,
                         "label_reason": pd.Series(reasons, dtype=object)})


def candidate_metrics(candidates: pd.DataFrame, background: pd.DataFrame,
                      settings: Mapping[str, Any],
                      sessions: Sequence[pd.Timestamp] | None = None) -> dict[str, Any]:
    """Top-K is evaluated per signal day against same-day eligible market rows."""
    horizon = settings["horizon_sessions"]
    target = settings["primary_target"]
    hit = target_name(target, horizon)
    outcome = primary_outcome_name(settings)
    def valid_outcome(frame: pd.DataFrame, *, allow_scalar: bool = False) -> pd.Series:
        valid = frame["label"].map(
            lambda label: (isinstance(label, Mapping) and label.get(outcome) is not None) or
            (allow_scalar and isinstance(label, (bool, np.bool_)))
        ).astype(bool)
        if "label_status" in frame:
            valid &= frame["label_status"].eq("labeled")
        return valid
    labeled_base = background[valid_outcome(background, allow_scalar=True)].copy()
    labeled_primary = candidates[valid_outcome(candidates)].copy()
    full_labels = candidates[valid_outcome(candidates)].copy()
    base_values = [row[outcome] if isinstance(row, Mapping) else row
                   for row in labeled_base["label"]]
    base_rate = float(np.mean(base_values)) if base_values else None
    flags = signal_event_flags(candidates, settings["event_cooldown_sessions"], sessions)
    event_candidates = candidates.loc[flags].copy()
    labeled_events = event_candidates[valid_outcome(event_candidates)]
    candidate_count, background_count, event_count = len(candidates), len(background), len(event_candidates)
    metrics: dict[str, Any] = {
        "candidate_count": int(candidate_count),
        "candidate_observation_count": int(candidate_count),
        "labeled_candidate_count": int(len(labeled_primary)),
        "censored_candidate_count": int(candidate_count - len(labeled_primary)),
        "candidate_censoring_rate": float((candidate_count - len(labeled_primary)) / candidate_count) if candidate_count else None,
        "background_count": int(background_count),
        "labeled_background_count": int(len(labeled_base)),
        "censored_background_count": int(background_count - len(labeled_base)),
        "background_censoring_rate": float((background_count - len(labeled_base)) / background_count) if background_count else None,
        "unique_signal_event_count": int(event_count),
        "labeled_signal_event_count": int(len(labeled_events)),
        "censored_signal_event_count": int(event_count - len(labeled_events)),
        "signal_event_censoring_rate": float((event_count - len(labeled_events)) / event_count) if event_count else None,
        "primary_target": hit,
        "primary_outcome": outcome,
        "success_rule": settings["success_rule"],
        "base_rate": base_rate,
        "label_version": LABEL_VERSION,
    }
    for k in settings["top_k_values"]:
        valid = labeled_primary[labeled_primary["rank"] <= k]
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
        # Raw daily rank is fixed before cooldown; repeats are removed without refilling Top-K.
        event_valid = labeled_events[labeled_events["rank"] <= k]
        event_precision = (float(np.mean([row[outcome] for row in event_valid["label"]]))
                           if len(event_valid) else None)
        metrics[f"event_top_{k}_count"] = int(len(event_valid))
        metrics[f"event_precision_at_{k}"] = event_precision
        metrics[f"event_lift_at_{k}"] = (event_precision / base_rate
                                           if event_precision is not None and base_rate else None)
    for name in (f"mfe_{horizon}", f"mae_{horizon}"):
        values = [row[name] for row in full_labels["label"] if name in row]
        metrics[f"average_{name}"] = float(np.mean(values)) if values else None
        metrics[f"median_{name}"] = float(np.median(values)) if values else None
    knife = [row["false_falling_knife"] for row in full_labels["label"]
             if row.get("false_falling_knife") is not None]
    metrics["false_falling_knife_rate"] = float(np.mean(knife)) if knife else None
    for threshold in settings["upside_targets"]:
        name = target_name(threshold, horizon)
        values = [row[name] for row in full_labels["label"] if name in row]
        metrics[f"{name}_rate"] = float(np.mean(values)) if values else None
        probability = f"p_{name}"
        if probability in full_labels:
            calibrated = full_labels[full_labels[probability].notna()]
            if len(calibrated):
                predicted = calibrated[probability].to_numpy(dtype=float)
                calibrated = calibrated[calibrated["label"].map(lambda row: name in row)]
                if calibrated.empty:
                    continue
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

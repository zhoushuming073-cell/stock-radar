"""Causal, inspectable first implementation of the complete Strategy 2 setup.

This model uses the seven lifecycle groups in the user's Phase 2 specification.
Its thresholds come from the pre-existing Train factor study and economic
interpretation of the setup, not from the previously viewed Test result.
Historical Test performance for this version is necessarily exploratory.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


REQUIRED = frozenset({
    "symbol", "tradability_pass", "elasticity_score",
    "ret_60", "drawdown_60", "drawdown_20", "pullback_days_20",
    "decline_speed_prev_3", "decline_acceleration", "red_body_avg_3",
    "red_body_avg_5", "range_contraction", "volume_contraction",
    "lower_wick_ratio", "close_location", "failed_breakdown",
    "support_reclaim", "new_low_frequency_5", "higher_low_proxy",
    "ret_1", "body_pct", "reclaim_ma_5", "rebound_from_low_5",
    "dist_ma_5", "close", "avg_dollar_volume_20",
})


@dataclass(frozen=True)
class FullStrategy2Rules:
    max_new: int = 3
    min_elasticity: float = 76.21433772581146  # Frozen pre-v3 Train threshold
    min_prior_peak_gain: float = 0.13230715023626216  # Frozen pre-v3 Train threshold
    min_pullback: float = 0.08
    max_pullback: float = 0.40
    max_new_low_frequency_5: float = 0.20
    max_rebound_from_5d_low: float = 0.15
    max_one_day_return: float = 0.10
    max_distance_from_ma5: float = 0.15
    min_close_location: float = 0.50
    min_wick_ratio: float = 0.25
    max_volume_contraction: float = 0.80
    exclude_explicit_funds: bool = False
    disabled_stages: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.max_new < 1 or not 0 < self.min_pullback < self.max_pullback < 1:
            raise ValueError("invalid Strategy 2 candidate limits")
        if not 0 <= self.max_new_low_frequency_5 <= 1:
            raise ValueError("invalid new-low limit")
        if self.exclude_explicit_funds:
            raise ValueError("current security names cannot filter historical candidates")
        known = {"prior_strength", "pullback_quality", "exhaustion",
                 "support_absorption", "new_low_stop", "early_reversal",
                 "not_extended", "elasticity"}
        if set(self.disabled_stages) - known:
            raise ValueError("unknown Strategy 2 ablation stage")


def _numeric(frame: pd.DataFrame, column: str) -> pd.Series:
    return pd.to_numeric(frame[column], errors="coerce").replace([np.inf, -np.inf], np.nan)


def _flag(frame: pd.DataFrame, column: str) -> pd.Series:
    return frame[column].eq(True).fillna(False)


def _scaled(value: pd.Series, start: float, end: float) -> pd.Series:
    return ((value - start) / (end - start)).clip(0, 1).fillna(0.0)


def score_full_strategy2(daily: pd.DataFrame, rules: FullStrategy2Rules) -> pd.DataFrame:
    """Score every signal-date row without reading forward labels or future bars."""
    missing = REQUIRED - set(daily)
    if missing:
        raise ValueError(f"missing full Strategy 2 inputs: {sorted(missing)}")
    frame = daily.copy()
    ret60 = _numeric(frame, "ret_60")
    dd60 = _numeric(frame, "drawdown_60")
    dd20 = _numeric(frame, "drawdown_20")
    prior_gain = ((1 + ret60) / (1 + dd60) - 1).where(dd60 > -1)
    frame["prior_peak_gain_60"] = prior_gain.replace([np.inf, -np.inf], np.nan)
    frame["prior_strength_score"] = _scaled(prior_gain, rules.min_prior_peak_gain, 0.50)

    depth = -dd20
    frame["pullback_quality_score"] = (
        1 - (depth - 0.18).abs() / 0.22
    ).clip(0, 1).fillna(0.0)

    previous_decline = _numeric(frame, "decline_speed_prev_3").lt(0)
    slowing = _numeric(frame, "decline_acceleration").gt(0)
    smaller_red_body = _numeric(frame, "red_body_avg_3").lt(_numeric(frame, "red_body_avg_5"))
    narrowing_range = _numeric(frame, "range_contraction").lt(1)
    frame["downside_exhaustion_score"] = (
        (previous_decline & slowing).astype(float) * 0.5
        + smaller_red_body.astype(float) * 0.25
        + narrowing_range.astype(float) * 0.25
    )

    wick_rejection = (_numeric(frame, "lower_wick_ratio").ge(rules.min_wick_ratio)
                      & _numeric(frame, "close_location").ge(rules.min_close_location))
    volume_fades = _numeric(frame, "volume_contraction").lt(rules.max_volume_contraction)
    failed_breakdown = _flag(frame, "failed_breakdown")
    support_reclaim = _flag(frame, "support_reclaim")
    absorption = failed_breakdown | support_reclaim | wick_rejection | volume_fades
    frame["support_absorption_score"] = (
        failed_breakdown.astype(float) + support_reclaim.astype(float)
        + wick_rejection.astype(float) + volume_fades.astype(float)
    ) / 4

    low_frequency = _numeric(frame, "new_low_frequency_5")
    frame["new_low_stop_score"] = (
        (1 - low_frequency).clip(0, 1).fillna(0.0)
        + _flag(frame, "higher_low_proxy").astype(float)
    ) / 2

    ret1 = _numeric(frame, "ret_1")
    green_body = _numeric(frame, "body_pct").gt(0)
    close_high = _numeric(frame, "close_location").ge(rules.min_close_location)
    early_up = ret1.gt(0) & green_body & close_high
    frame["early_reversal_score"] = (
        ret1.gt(0).astype(float) + green_body.astype(float)
        + close_high.astype(float)
        + (_flag(frame, "higher_low_proxy") | _flag(frame, "reclaim_ma_5")).astype(float)
    ) / 4

    rebound = _numeric(frame, "rebound_from_low_5")
    ma_distance = _numeric(frame, "dist_ma_5")
    not_extended = (rebound.le(rules.max_rebound_from_5d_low)
                    & ret1.le(rules.max_one_day_return)
                    & ma_distance.le(rules.max_distance_from_ma5))
    frame["not_extended_score"] = (
        (1 - rebound / rules.max_rebound_from_5d_low).clip(0, 1).fillna(0.0)
        + (1 - ret1 / rules.max_one_day_return).clip(0, 1).fillna(0.0)
        + (1 - ma_distance / rules.max_distance_from_ma5).clip(0, 1).fillna(0.0)
    ) / 3

    frame["strategy2_score"] = 100 * (
        0.15 * frame["prior_strength_score"]
        + 0.20 * frame["pullback_quality_score"]
        + 0.15 * frame["downside_exhaustion_score"]
        + 0.15 * frame["support_absorption_score"]
        + 0.10 * frame["new_low_stop_score"]
        + 0.20 * frame["early_reversal_score"]
        + 0.05 * frame["not_extended_score"]
    )
    disabled = set(rules.disabled_stages)
    if disabled:
        components = {
            "prior_strength": (0.15, "prior_strength_score"),
            "pullback_quality": (0.20, "pullback_quality_score"),
            "exhaustion": (0.15, "downside_exhaustion_score"),
            "support_absorption": (0.15, "support_absorption_score"),
            "new_low_stop": (0.10, "new_low_stop_score"),
            "early_reversal": (0.20, "early_reversal_score"),
            "not_extended": (0.05, "not_extended_score"),
        }
        active = [(weight, column) for stage, (weight, column) in components.items()
                  if stage not in disabled]
        if active:
            total_weight = sum(weight for weight, _ in active)
            frame["strategy2_score"] = 100 * sum(
                weight * frame[column] for weight, column in active
            ) / total_weight
        else:
            frame["strategy2_score"] = 0.0

    liquid = _flag(frame, "tradability_pass")
    elastic = _numeric(frame, "elasticity_score").ge(rules.min_elasticity)
    prior = prior_gain.ge(rules.min_prior_peak_gain)
    pullback = (depth.between(rules.min_pullback, rules.max_pullback)
                & _numeric(frame, "pullback_days_20").ge(2))
    exhaustion = previous_decline & slowing
    stopped_lows = low_frequency.le(rules.max_new_low_frequency_5)
    eligible = (liquid & elastic & prior & pullback & exhaustion & absorption
                & stopped_lows & early_up & not_extended)
    if disabled:
        stages = {
            "elasticity": elastic, "prior_strength": prior,
            "pullback_quality": pullback, "exhaustion": exhaustion,
            "support_absorption": absorption, "new_low_stop": stopped_lows,
            "early_reversal": early_up, "not_extended": not_extended,
        }
        eligible = liquid.copy()
        for name, mask in stages.items():
            if name not in disabled:
                eligible &= mask
    stages = {
        "tradable": liquid,
        "elasticity": elastic,
        "prior_strength": prior,
        "pullback": pullback,
        "exhaustion": exhaustion,
        "support_absorption": absorption,
        "new_low_stop": stopped_lows,
        "early_reversal": early_up,
        "not_extended": not_extended,
    }
    for name, mask in stages.items():
        active = name not in disabled or name in {"tradable", "fund_filter"}
        frame[f"filter_pass_{name}"] = (
            mask.fillna(False).astype(bool) if active
            else pd.Series(True, index=frame.index))
    frame["strategy2_eligible"] = eligible.fillna(False)
    return frame


def rank_full_strategy2(
    daily: pd.DataFrame, rules: FullStrategy2Rules,
    *, already_held: set[str] | None = None,
) -> pd.DataFrame:
    """Select up to three eligible names; ties break by symbol."""
    scored = score_full_strategy2(daily, rules)
    selected = scored.loc[scored["strategy2_eligible"]]
    if already_held:
        selected = selected.loc[~selected["symbol"].isin(already_held)]
    return selected.reset_index(drop=True).sort_values(
        ["strategy2_score", "symbol"], ascending=[False, True]
    ).head(rules.max_new)

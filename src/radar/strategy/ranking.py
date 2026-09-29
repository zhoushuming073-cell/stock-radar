"""Transparent Strategy 2 candidate rules frozen before a final-test run."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CandidateRules:
    elasticity_min: float
    drawdown_20_max: float
    max_new: int
    exclude_explicit_etf_etn_names: bool = False
    trend_elasticity_min: float = 60.0
    trend_ret_60_min: float = 0.037
    trend_drawdown_20_min: float = -0.20
    trend_drawdown_20_max: float = -0.05
    trend_close_location_min: float = 0.50


def rank_candidates(
    daily: pd.DataFrame, rules: CandidateRules, *, variant: str,
    already_held: set[str] | None = None,
) -> pd.DataFrame:
    """Return at most ``max_new`` signals formed with date-t information only.

    The context limits were chosen from Train factor distributions and checked
    on Validation; ``reversal_confirmed`` is a separately measured variant.
    No outcome column is read here.
    """
    needed = {"symbol", "elasticity_score", "drawdown_20", "ret_1",
              "close_location", "tradability_pass"}
    if not needed.issubset(daily):
        raise ValueError(f"missing signal inputs: {sorted(needed - set(daily))}")
    if rules.max_new < 1:
        raise ValueError("max_new must be positive")
    if rules.exclude_explicit_etf_etn_names:
        raise ValueError("current security names cannot filter historical candidates")
    if variant == "trend_reversal":
        if "ret_60" not in daily:
            raise ValueError("trend_reversal requires ret_60")
        eligible = (daily["tradability_pass"].eq(True)
                    & daily["elasticity_score"].ge(rules.trend_elasticity_min)
                    & daily["ret_60"].ge(rules.trend_ret_60_min)
                    & daily["drawdown_20"].between(rules.trend_drawdown_20_min,
                                                       rules.trend_drawdown_20_max)
                    & daily["ret_1"].gt(0)
                    & daily["close_location"].ge(rules.trend_close_location_min))
    else:
        eligible = (daily["tradability_pass"].eq(True)
                    & daily["elasticity_score"].ge(rules.elasticity_min)
                    & daily["drawdown_20"].le(rules.drawdown_20_max))
    frame = daily.loc[eligible].copy()
    if already_held:
        frame = frame.loc[~frame["symbol"].isin(already_held)]
    if variant == "reversal_confirmed":
        frame = frame.loc[frame["ret_1"].gt(0) & frame["close_location"].ge(0.5)]
    elif variant not in {"elastic_rank", "drawdown_rank", "combined_rank", "trend_reversal"}:
        raise ValueError(f"unknown candidate variant: {variant}")
    if frame.empty:
        return frame.assign(strategy2_score=pd.Series(dtype=float))
    elastic_rank = frame["elasticity_score"].rank(pct=True)
    depth_rank = (-frame["drawdown_20"]).rank(pct=True)
    if variant == "elastic_rank":
        frame["strategy2_score"] = elastic_rank * 100
    elif variant == "drawdown_rank":
        frame["strategy2_score"] = depth_rank * 100
    elif variant == "trend_reversal":
        frame["strategy2_score"] = (
            frame["ret_60"].rank(pct=True) + elastic_rank
        ) * 50
    else:
        frame["strategy2_score"] = (elastic_rank + depth_rank) * 50
    return frame.reset_index(drop=True).sort_values(
        ["strategy2_score", "symbol"], ascending=[False, True]
    ).head(rules.max_new)

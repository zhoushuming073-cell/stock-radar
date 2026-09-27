"""Example Stock Radar plugin: signals use only the current causal context."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from radar.strategy.base import StrategyPlugin
from radar.strategy.context import StrategyContext


class ExampleMeasuredPullback(StrategyPlugin):
    def required_features(self) -> set[str]:
        return {"tradability_pass", "ret_60", "drawdown_20"}

    def hard_filter(
        self, context: StrategyContext, config: Mapping[str, Any]
    ) -> pd.Series:
        frame = context.frame
        minimum_return = float(config["prior_strength"]["min_return_60"])
        minimum_depth = float(config["pullback"]["min_depth"])
        maximum_depth = float(config["pullback"]["max_depth"])
        if not 0 <= minimum_depth < maximum_depth < 1:
            raise ValueError("pullback depth must satisfy 0 <= min < max < 1")

        prior_return = pd.to_numeric(frame["ret_60"], errors="coerce")
        drawdown = pd.to_numeric(frame["drawdown_20"], errors="coerce")
        return (
            frame["tradability_pass"].eq(True)
            & prior_return.ge(minimum_return)
            & drawdown.between(-maximum_depth, -minimum_depth)
        ).fillna(False).astype(bool)

    def score(
        self, context: StrategyContext, config: Mapping[str, Any]
    ) -> pd.Series:
        # Higher 60-session return ranks ahead. Missing values stay missing and
        # cannot pass hard_filter; no future return is read here.
        return pd.to_numeric(context.frame["ret_60"], errors="coerce")

    def select(
        self, candidates: pd.DataFrame, config: Mapping[str, Any]
    ) -> pd.DataFrame:
        maximum = config["selection"]["max_candidates"]
        if maximum is not None and (isinstance(maximum, bool) or not isinstance(maximum, int) or maximum < 0):
            raise ValueError("max_candidates must be a non-negative integer or null")
        return (
            candidates.sort_values(
                ["strategy_score", "symbol"], ascending=[False, True], kind="stable"
            )
            .head(maximum if maximum is not None else len(candidates))
            .copy()
        )


PLUGIN = ExampleMeasuredPullback()

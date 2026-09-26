"""Adapter for the frozen Phase 2 Strategy 2 signal implementation."""

from __future__ import annotations

from typing import Any, Mapping

import pandas as pd

from radar.strategy.base import StrategyPlugin
from radar.strategy.context import StrategyContext
from radar.strategy.full_strategy2 import FullStrategy2Rules, REQUIRED, score_full_strategy2


class FullStrategy2Plugin(StrategyPlugin):
    def required_features(self) -> set[str]:
        return set(REQUIRED - {"symbol", "security_name", "close"})

    @staticmethod
    def _rules(config: Mapping[str, Any]) -> FullStrategy2Rules:
        names = FullStrategy2Rules.__dataclass_fields__
        return FullStrategy2Rules(**{name: config[name] for name in names})

    def hard_filter(self, context: StrategyContext, config: Mapping[str, Any]) -> pd.Series:
        return score_full_strategy2(context.frame, self._rules(config))["strategy2_eligible"]

    def score(self, context: StrategyContext, config: Mapping[str, Any]) -> pd.Series:
        return score_full_strategy2(context.frame, self._rules(config))["strategy2_score"]

    def select(self, candidates: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
        return candidates.sort_values(
            ["strategy_score", "symbol"], ascending=[False, True]
        ).head(int(config["max_new"])).copy()


PLUGIN = FullStrategy2Plugin()

"""Adapter for the frozen Phase 2 Strategy 2 signal implementation."""
from __future__ import annotations
from typing import Any, Mapping
import pandas as pd
from qc_base import StrategyPlugin
from qc_context import StrategyContext
from qc_full_strategy2 import FullStrategy2Rules, REQUIRED, score_full_strategy2

class FullStrategy2Plugin(StrategyPlugin):

    def required_features(self) -> set[str]:
        return set(REQUIRED - {'symbol', 'security_name', 'close'})

    @staticmethod
    def _rules(config: Mapping[str, Any]) -> FullStrategy2Rules:
        names = FullStrategy2Rules.__dataclass_fields__
        return FullStrategy2Rules(**{name: config[name] for name in names if name in config})

    def hard_filter(self, context: StrategyContext, config: Mapping[str, Any]) -> pd.Series:
        return score_full_strategy2(context.frame, self._rules(config))['strategy2_eligible']

    def score(self, context: StrategyContext, config: Mapping[str, Any]) -> pd.Series:
        return score_full_strategy2(context.frame, self._rules(config))['strategy2_score']

    def select(self, candidates: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
        selection = config.get('selection')
        maximum = selection.get('max_candidates') if isinstance(selection, Mapping) else config['max_new']
        return candidates.sort_values(['strategy_score', 'symbol'], ascending=[False, True]).head(len(candidates) if maximum is None else int(maximum)).copy()

    def diagnostic_scores(self, context: StrategyContext, config: Mapping[str, Any]) -> pd.DataFrame:
        scored = score_full_strategy2(context.frame, self._rules(config))
        columns = [name for name in scored if name.endswith('_score') and name != 'strategy2_score']
        return scored[columns].copy()

    def filter_diagnostics(self, context: StrategyContext, config: Mapping[str, Any]) -> pd.DataFrame:
        scored = score_full_strategy2(context.frame, self._rules(config))
        columns = [name for name in scored if name.startswith('filter_pass_')]
        return scored[columns].copy()
PLUGIN = FullStrategy2Plugin()

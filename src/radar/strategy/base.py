"""Public interface implemented by research strategy plugins."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

import pandas as pd

from radar.strategy.context import StrategyContext


class StrategyPlugin(ABC):
    """Select candidates using only the signal-day context and configuration."""

    @abstractmethod
    def required_features(self) -> set[str]:
        """Names of causal features read by this plugin."""

    @abstractmethod
    def hard_filter(
        self, context: StrategyContext, config: Mapping[str, Any]
    ) -> pd.Series:
        """Boolean eligibility mask aligned to ``context.frame``."""

    @abstractmethod
    def score(
        self, context: StrategyContext, config: Mapping[str, Any]
    ) -> pd.Series:
        """Numeric scores aligned to ``context.frame``; larger ranks higher."""

    @abstractmethod
    def select(
        self, candidates: pd.DataFrame, config: Mapping[str, Any]
    ) -> pd.DataFrame:
        """Ordered subset of eligible candidates, possibly empty."""

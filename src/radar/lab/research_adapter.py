"""Additive past-only plugin context; frozen interface-v1 files stay unchanged."""
from __future__ import annotations

from collections.abc import Mapping

import numpy as np
import pandas as pd

from radar.strategy.context import StrategyContext
from radar.strategy.validation import is_future_feature


class ResearchStrategyContext(StrategyContext):
    __slots__ = ("_history_capability",)

    def __init__(self, signal_date: pd.Timestamp, frame: pd.DataFrame, history):
        super().__init__(signal_date, frame)
        object.__setattr__(self, "_history_capability", history)

    def history(self, security_id: str, sessions: int = 430) -> pd.DataFrame:
        if isinstance(sessions, bool) or not isinstance(sessions, int) or not 1 <= sessions <= 430:
            raise ValueError("history sessions must be 1..430")
        frame = self.frame
        if "security_id" not in frame or str(security_id) not in set(frame.security_id.astype(str)):
            raise ValueError("history is limited to dated securities in this signal context")
        result = self._history_capability(str(security_id), self.signal_date, sessions)
        if not isinstance(result, pd.DataFrame) or result.empty or "date" not in result:
            raise ValueError("host history is unavailable")
        if pd.to_datetime(result.date).gt(self.signal_date).any():
            raise ValueError("host history contains post-signal data")
        return result.copy(deep=True)


def evaluate_research_selection(plugin, config: Mapping, daily: pd.DataFrame,
                                history) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Use the legacy selection contract with a separate, opted-in context."""
    required = set(plugin.required_features())
    if not required or any(is_future_feature(name) for name in required):
        raise ValueError("research plugin requested invalid causal features")
    columns = ["symbol", "security_name", "close", "security_id", *sorted(required)]
    if set(columns) - set(daily):
        raise ValueError(f"missing research features: {sorted(set(columns)-set(daily))}")
    if daily.empty:
        return daily.iloc[0:0].copy(), daily.iloc[0:0].copy()
    if daily.date.nunique() != 1 or daily.symbol.duplicated().any():
        raise ValueError("research selector requires one unambiguous signal day")
    causal = daily[columns].reset_index(drop=True).copy()
    causal["security_name"] = causal["symbol"]
    context = ResearchStrategyContext(pd.Timestamp(daily.date.iloc[0]), causal, history)
    eligible = plugin.hard_filter(context, config)
    scores = plugin.score(context, config)
    if not isinstance(eligible, pd.Series) or not eligible.index.equals(causal.index):
        raise ValueError("research hard_filter must be index-aligned")
    if not pd.api.types.is_bool_dtype(eligible.dtype) or eligible.isna().any():
        raise ValueError("research hard_filter must be non-null boolean")
    if not isinstance(scores, pd.Series) or not scores.index.equals(causal.index):
        raise ValueError("research score must be index-aligned")
    numeric = pd.to_numeric(scores, errors="coerce")
    if not np.isfinite(numeric.loc[eligible].to_numpy(dtype=float)).all():
        raise ValueError("research eligible scores must be finite")
    candidates = causal.loc[eligible].copy()
    candidates["strategy_score"] = numeric.loc[eligible]
    selected = plugin.select(candidates.copy(deep=True), config)
    if not isinstance(selected, pd.DataFrame) or not selected.index.is_unique:
        raise ValueError("research select must return unique candidate rows")
    if not selected.index.isin(candidates.index).all() or list(selected.columns) != list(candidates.columns):
        raise ValueError("research select fabricated or changed candidate columns")
    pd.testing.assert_frame_equal(selected, candidates.loc[selected.index])
    maximum = config.get("selection", {}).get("max_candidates")
    if maximum is not None and len(selected) > maximum:
        raise ValueError("research selection exceeded its candidate cap")
    ranked = candidates.sort_values(["strategy_score", "symbol"],
                                    ascending=[False, True], kind="stable").reset_index(drop=True)
    ranked["rank"] = np.arange(1, len(ranked) + 1)
    ranked["selected"] = ranked.symbol.isin(selected.symbol)
    return ranked, selected

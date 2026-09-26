"""Narrow bridge from causal strategy plugins to the unchanged execution engine."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

import numpy as np
import pandas as pd

from radar.strategy.base import StrategyPlugin
from radar.strategy.context import StrategyContext


BASE_COLUMNS = frozenset({"symbol", "security_name", "close"})


def make_candidate_selector(
    plugin: StrategyPlugin,
    config: Mapping[str, Any],
    *,
    max_new: int = 3,
) -> Callable[[pd.DataFrame, set[str]], pd.DataFrame]:
    """Expose only declared t-close columns; execution fields stay host-owned."""
    if not 0 <= max_new <= 3:
        raise ValueError("execution policy permits at most 3 new candidates")
    required = set(plugin.required_features())
    if not required or not all(isinstance(name, str) for name in required):
        raise ValueError("required_features must contain causal feature names")
    if required & {"open", "high", "low", "forward_labels"}:
        raise ValueError("strategy requested an execution or future-data field")

    def select(daily: pd.DataFrame, already_held: set[str]) -> pd.DataFrame:
        missing = (BASE_COLUMNS | required) - set(daily.columns)
        if missing:
            raise ValueError(f"missing required strategy features: {sorted(missing)}")
        if daily.empty:
            return daily.iloc[0:0].copy()
        if "date" not in daily.columns or daily["date"].nunique() != 1:
            raise ValueError("strategy selector requires one signal date")
        columns = ["symbol", "security_name", "close", *sorted(required - BASE_COLUMNS)]
        context = StrategyContext(pd.Timestamp(daily["date"].iloc[0]),
                                  daily[columns].reset_index(drop=True))
        frame = context.frame
        eligible = plugin.hard_filter(context, config)
        scores = plugin.score(context, config)
        if not isinstance(eligible, pd.Series) or not eligible.index.equals(frame.index):
            raise ValueError("hard_filter must return an index-aligned Series")
        if not pd.api.types.is_bool_dtype(eligible.dtype) or eligible.isna().any():
            raise ValueError("hard_filter must return non-null booleans")
        if not isinstance(scores, pd.Series) or not scores.index.equals(frame.index):
            raise ValueError("score must return an index-aligned Series")
        numeric = pd.to_numeric(scores, errors="coerce")
        chosen_mask = eligible & ~frame["symbol"].isin(already_held)
        if not np.isfinite(numeric.loc[chosen_mask].to_numpy(dtype=float)).all():
            raise ValueError("eligible strategy scores must be finite")
        candidates = frame.loc[chosen_mask].copy()
        candidates["strategy_score"] = numeric.loc[chosen_mask]
        selected = plugin.select(candidates.copy(), config)
        if not isinstance(selected, pd.DataFrame) or "symbol" not in selected or "strategy_score" not in selected:
            raise ValueError("select must return candidate rows with scores")
        if len(selected) > max_new or selected["symbol"].duplicated().any():
            raise ValueError("strategy exceeded new-candidate limit or duplicated symbols")
        if not set(selected["symbol"]).issubset(set(candidates["symbol"])):
            raise ValueError("strategy selected a symbol outside its eligible candidates")
        expected = candidates.set_index("symbol")["strategy_score"]
        for row in selected.itertuples(index=False):
            if not np.isclose(float(row.strategy_score), float(expected.loc[row.symbol]), rtol=0, atol=0):
                raise ValueError("strategy altered a candidate score")
        output = daily.set_index("symbol", drop=False).loc[selected["symbol"].tolist()].copy()
        output["strategy2_score"] = selected["strategy_score"].to_numpy(dtype=float)
        return output.reset_index(drop=True)

    return select

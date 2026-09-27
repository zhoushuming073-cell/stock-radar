"""Narrow bridge from causal strategy plugins to the unchanged execution engine."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import re
from typing import Any

import numpy as np
import pandas as pd

from radar.strategy.base import StrategyPlugin
from radar.strategy.context import StrategyContext
from radar.strategy.validation import is_future_feature


BASE_COLUMNS = frozenset({"symbol", "security_name", "close"})
_DIAGNOSTIC_NAME = re.compile(r"^[a-z][a-z0-9_]*$")


def evaluate_selection(plugin: StrategyPlugin, config: Mapping[str, Any],
                       daily: pd.DataFrame, already_held: set[str] | None = None,
                       *, diagnostics: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return every eligible scored row and the plugin's selected subset.

    The plugin receives only its declared causal columns. Backtest and Scanner
    call this same selection path, with separate host-owned work afterward.
    """
    required = set(plugin.required_features())
    if not required or not all(isinstance(name, str) for name in required):
        raise ValueError("required_features must contain causal feature names")
    if any(is_future_feature(name) for name in required) or required & {"open", "high", "low"}:
        raise ValueError("strategy requested an execution or future-data field")
    missing = (BASE_COLUMNS | required) - set(daily.columns)
    if missing:
        raise ValueError(f"missing required strategy features: {sorted(missing)}")
    if daily.empty:
        return daily.iloc[0:0].copy(), daily.iloc[0:0].copy()
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
    mask = eligible & ~frame["symbol"].isin(already_held or set())
    if not np.isfinite(numeric.loc[mask].to_numpy(dtype=float)).all():
        raise ValueError("eligible strategy scores must be finite")
    candidates = frame.loc[mask].copy()
    candidates["strategy_score"] = numeric.loc[mask]
    selected = plugin.select(candidates.copy(deep=True), config)
    if not isinstance(selected, pd.DataFrame) or "symbol" not in selected or "strategy_score" not in selected:
        raise ValueError("select must return candidate rows with scores")
    if selected["symbol"].duplicated().any():
        raise ValueError("strategy duplicated a candidate")
    if not set(selected["symbol"]).issubset(set(candidates["symbol"])):
        raise ValueError("strategy selected a symbol outside its eligible candidates")
    expected = candidates.set_index("symbol")["strategy_score"]
    for row in selected.itertuples(index=False):
        if not np.isclose(float(row.strategy_score), float(expected.loc[row.symbol]), rtol=0, atol=0):
            raise ValueError("strategy altered a candidate score")
    maximum = config.get("selection", {}).get("max_candidates") if isinstance(config.get("selection", {}), Mapping) else None
    if maximum is not None and len(selected) > maximum:
        raise ValueError("strategy exceeded selection.max_candidates")
    ranked = candidates.sort_values(["strategy_score", "symbol"],
                                    ascending=[False, True], kind="stable").reset_index(drop=True)
    ranked["rank"] = np.arange(1, len(ranked) + 1)
    ranked["selected"] = ranked["symbol"].isin(selected["symbol"])
    if diagnostics and callable(getattr(plugin, "diagnostic_scores", None)):
        extra = plugin.diagnostic_scores(context, config)
        if not isinstance(extra, pd.DataFrame) or not extra.index.equals(frame.index):
            raise ValueError("diagnostic_scores must return an index-aligned DataFrame")
        for name in extra:
            if not _DIAGNOSTIC_NAME.fullmatch(str(name)) or is_future_feature(str(name)):
                raise ValueError(f"invalid diagnostic column: {name}")
            series = pd.to_numeric(extra[name], errors="coerce")
            if not np.isfinite(series.loc[mask].to_numpy(dtype=float)).all():
                raise ValueError(f"diagnostic column must contain finite scores: {name}")
            if str(name).startswith("p_") and not series.loc[mask].between(0, 1).all():
                raise ValueError(f"probability must be between 0 and 1: {name}")
            mapped = ranked["symbol"].map(dict(zip(frame["symbol"], series)))
            if name in ranked.columns:
                if not np.array_equal(ranked[name].to_numpy(), mapped.to_numpy()):
                    raise ValueError(f"diagnostic column conflicts with causal input: {name}")
            else:
                ranked[name] = mapped
        ranked.attrs["diagnostic_columns"] = list(extra.columns)
    return ranked, selected


def make_candidate_selector(
    plugin: StrategyPlugin,
    config: Mapping[str, Any],
    *,
    max_new: int = 3,
) -> Callable[[pd.DataFrame, set[str]], pd.DataFrame]:
    """Expose only declared t-close columns; execution fields stay host-owned."""
    if isinstance(max_new, bool) or not isinstance(max_new, int) or max_new < 0:
        raise ValueError("max_new must be a non-negative integer")
    required = set(plugin.required_features())
    if any(is_future_feature(name) for name in required) or required & {"open", "high", "low"}:
        raise ValueError("strategy requested an execution or future-data field")

    def select(daily: pd.DataFrame, already_held: set[str]) -> pd.DataFrame:
        _, selected = evaluate_selection(plugin, config, daily, already_held)
        if len(selected) > max_new:
            raise ValueError("strategy exceeded new-candidate limit")
        output = daily.set_index("symbol", drop=False).loc[selected["symbol"].tolist()].copy()
        output["strategy2_score"] = selected["strategy_score"].to_numpy(dtype=float)
        return output.reset_index(drop=True)

    return select

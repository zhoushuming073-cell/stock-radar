from typing import Any, Mapping

import pandas as pd
import pytest

from radar.strategy.adapter import evaluate_selection, make_candidate_selector
from radar.strategy.base import StrategyPlugin
from radar.strategy.context import StrategyContext


class ProbeStrategy(StrategyPlugin):
    seen_columns: set[str] = set()

    def required_features(self) -> set[str]:
        return {"ret_1"}

    def hard_filter(self, context: StrategyContext, config: Mapping[str, Any]) -> pd.Series:
        self.seen_columns = set(context.frame.columns)
        return context.frame["ret_1"].gt(config["minimum"])

    def score(self, context: StrategyContext, config: Mapping[str, Any]) -> pd.Series:
        return context.frame["ret_1"]

    def select(self, candidates: pd.DataFrame, config: Mapping[str, Any]) -> pd.DataFrame:
        return candidates.sort_values(["strategy_score", "symbol"], ascending=[False, True]).head(3)


def _daily(future=999.0) -> pd.DataFrame:
    return pd.DataFrame({
        "date": [pd.Timestamp("2025-01-02")] * 2,
        "symbol": ["B", "A"],
        "security_name": ["B Inc", "A Inc"],
        "close": [10.0, 20.0],
        "ret_1": [0.10, 0.20],
        "open": [9.0, 19.0],
        "forward_labels": [future, -future],
    }).set_index("symbol", drop=False)


def test_plugin_only_sees_declared_causal_features_and_future_mutation_does_not_change_signal():
    plugin = ProbeStrategy()
    selector = make_candidate_selector(plugin, {"minimum": 0.0})
    first = selector(_daily(), set())
    second = selector(_daily(-123.0), set())
    assert plugin.seen_columns == {"symbol", "security_name", "close", "ret_1"}
    assert first["symbol"].tolist() == second["symbol"].tolist() == ["A", "B"]
    assert first["strategy2_score"].tolist() == [0.20, 0.10]
    assert selector(_daily(), {"A"})["symbol"].tolist() == ["B"]


def test_plugin_cannot_request_future_feature():
    plugin = ProbeStrategy()
    plugin.required_features = lambda: {"forward_labels"}
    with pytest.raises(ValueError, match="future-data"):
        make_candidate_selector(plugin, {})


def test_current_security_name_is_display_only_even_for_legacy_name_filter():
    class LegacyNameStrategy(ProbeStrategy):
        def hard_filter(self, context, config):
            return ~context.frame["security_name"].str.contains("ETF")

        def score(self, context, config):
            return context.frame["security_name"].str.len().astype(float)

    plugin = LegacyNameStrategy()
    before = _daily().reset_index(drop=True)
    future = before.assign(security_name="Future Leveraged ETF")
    first, _ = evaluate_selection(plugin, {}, before)
    second, _ = evaluate_selection(plugin, {}, future)
    assert first["symbol"].tolist() == second["symbol"].tolist()
    assert first["strategy_score"].tolist() == second["strategy_score"].tolist()
    assert first["security_name"].tolist() == ["A Inc", "B Inc"]
    assert second["security_name"].tolist() == ["Future Leveraged ETF"] * 2

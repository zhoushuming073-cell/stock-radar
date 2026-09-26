"""Small contract checks for the Strategy Lab presentation adapters."""

import pandas as pd
import pytest

from radar.strategy_lab_ui import equity_curve, parameter_diff, _plain


def test_live_equity_curve_grows_from_progress_events():
    events = [
        {"kind": "progress", "payload": {"date": "2024-01-02", "equity": 1_000_000, "cash": 500_000}},
        {"kind": "progress", "payload": {"date": "2024-01-03", "equity": 900_000, "cash": 400_000}},
        {"kind": "started", "payload": {}},
    ]
    curve = equity_curve([], events, 1_000_000)
    assert curve["equity"].tolist() == [1_000_000, 900_000]
    assert curve["drawdown"].tolist() == pytest.approx([0.0, -0.1])


def test_final_equity_rows_take_precedence_over_progress():
    stored = pd.DataFrame([{"date": "2024-01-02", "equity": 1_100_000,
                            "cash": 300_000}])
    events = [{"kind": "progress", "payload": {"date": "2024-01-02",
                                                "equity": 1_000_000}}]
    curve = equity_curve(stored, events, 1_000_000)
    assert len(curve) == 1
    assert curve["equity"].iloc[0] == 1_100_000


def test_parameter_diff_only_contains_changed_leaf_values():
    runs = [
        {"run_id": "a", "metadata": {"config": {"pullback": {"max": 0.3},
                                            "selection": {"max_candidates": 3}}}},
        {"run_id": "b", "metadata": {"config": {"pullback": {"max": 0.4},
                                            "selection": {"max_candidates": 3}}}},
    ]
    table = parameter_diff(runs)
    assert table["参数"].tolist() == ["strategy.pullback.max"]
    assert table["a"].tolist() == [0.3]
    assert table["b"].tolist() == [0.4]


def test_read_only_config_becomes_editable_copy():
    from types import MappingProxyType

    source = MappingProxyType({"pullback": MappingProxyType({"max": 0.3})})
    draft = _plain(source)
    draft["pullback"]["max"] = 0.4
    assert source["pullback"]["max"] == 0.3

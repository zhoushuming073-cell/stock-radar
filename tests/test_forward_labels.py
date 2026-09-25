import numpy as np
import pandas as pd

from radar.labels.forward import compute_forward_labels


def bars(rows):
    return pd.DataFrame(rows, columns=["open", "high", "low", "close"],
                        index=pd.bdate_range("2026-01-02", periods=len(rows)))


def test_high_only_does_not_trigger_executable_take_profit():
    data = bars([[100, 101, 99, 100]] + [[100, 108, 98, 103]] * 10)
    result = compute_forward_labels(data).iloc[0]
    assert np.isclose(result["mfe_high_5d"], 0.08)
    assert result["exec_hit_tp_5d"] == False  # noqa: E712
    assert result["simulated_exit_reason"] == "max_holding_period"
    assert np.isclose(result["simulated_gross_return"], 0.03)


def test_gap_exit_gets_actual_open_and_entry_open_cannot_exit():
    data = bars([[100, 100, 100, 100], [110, 110, 109, 109],
                 [116, 117, 115, 116]] + [[116, 116, 116, 116]] * 8)
    result = compute_forward_labels(data).iloc[0]
    assert result["entry_open"] == 110
    assert result["simulated_exit_reason"] == "take_profit_gap"
    assert result["simulated_exit_price"] == 116
    assert np.isclose(result["simulated_gross_return"], 116 / 110 - 1)
    assert result["exec_hit_tp_5d"] == True  # noqa: E712


def test_missing_future_bar_does_not_skip_path_or_fabricate_label():
    rows = [[100, 100, 100, 100]] + [[100, 101, 99, 100]] * 10
    rows[3] = [np.nan] * 4
    result = compute_forward_labels(bars(rows)).iloc[0]
    assert np.isnan(result["return_close_5d"])
    assert pd.isna(result["exec_hit_tp_5d"])
    assert result["simulated_exit_reason"] is None


def test_future_does_not_change_earlier_features_but_can_change_labels():
    data = bars([[100, 101, 99, 100]] + [[100, 101, 99, 100]] * 10)
    changed = data.copy()
    changed.iloc[5, 3] = 120
    changed.iloc[5, 1] = 120
    assert compute_forward_labels(data).iloc[0]["return_close_5d"] == 0
    assert np.isclose(compute_forward_labels(changed).iloc[0]["return_close_5d"], 0.2)

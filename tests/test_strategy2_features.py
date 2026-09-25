import numpy as np
import pandas as pd

from radar.features.strategy2 import compute_strategy2_features


def sample(n=75):
    dates = pd.bdate_range("2025-01-01", periods=n)
    price = np.arange(100.0, 100.0 + n)
    bars = pd.DataFrame({"high": price + 2, "low": price - 2,
                         "close": price}, index=dates)
    spy = pd.Series(np.arange(200.0, 200.0 + n), index=dates)
    qqq = pd.Series(np.arange(300.0, 300.0 + n), index=dates)
    return bars, spy, qqq


def test_relative_strength_and_pullback_are_causal():
    bars, spy, qqq = sample()
    out = compute_strategy2_features(bars, spy, qqq)
    expected = (bars.close.iloc[40] / bars.close.iloc[20] - 1) - (spy.iloc[40] / spy.iloc[20] - 1)
    assert np.isclose(out["relative_strength_spy_20"].iloc[40], expected)
    assert out["pullback_days_20"].iloc[40] == 0
    bars2 = pd.concat([bars, pd.DataFrame({"high": [1000.], "low": [1.], "close": [500.]},
                                          index=[bars.index[-1] + pd.offsets.BDay(1)])])
    spy2 = pd.concat([spy, pd.Series([400.], index=bars2.index[-1:])])
    qqq2 = pd.concat([qqq, pd.Series([500.], index=bars2.index[-1:])])
    pd.testing.assert_frame_equal(out, compute_strategy2_features(bars2, spy2, qqq2).iloc[:-1],
                                  check_freq=False)

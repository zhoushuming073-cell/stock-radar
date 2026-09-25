import numpy as np
import pandas as pd

from radar.features.base import compute_base_features


def sample(n=70):
    dates = pd.bdate_range("2025-01-01", periods=n)
    close = np.arange(100.0, 100.0 + n)
    return pd.DataFrame({"open": close - 1, "high": close + 2,
                         "low": close - 2, "close": close, "volume": 1000.0},
                        index=dates)


def test_known_rolling_quantities_and_no_partial_warmup():
    out = compute_base_features(sample())
    assert np.isnan(out["ma_20"].iloc[18])
    assert np.isclose(out["ma_20"].iloc[19], np.arange(100, 120).mean())
    assert np.isclose(out["atr_20"].iloc[19], 4.0)
    assert np.isclose(out["lower_wick_ratio"].iloc[19], 0.25)
    assert np.isclose(out["close_location"].iloc[19], 0.5)


def test_zero_range_and_missing_session_do_not_create_values():
    bars = sample()
    bars.iloc[20, :4] = 120
    bars.iloc[21, :] = np.nan
    out = compute_base_features(bars)
    assert np.isnan(out["close_location"].iloc[20])
    assert np.isnan(out["ret_1"].iloc[22])
    assert np.isnan(out["atr_20"].iloc[22])
    assert np.isnan(out["down_volume_ratio"].iloc[22])


def test_appended_future_bar_cannot_change_earlier_features():
    bars = sample()
    earlier = compute_base_features(bars)
    later = pd.concat([bars, pd.DataFrame({"open": [1000.], "high": [2000.],
                                           "low": [1.], "close": [1500.], "volume": [1e9]},
                                          index=[bars.index[-1] + pd.offsets.BDay(1)])])
    pd.testing.assert_frame_equal(earlier, compute_base_features(later).iloc[:-1], check_freq=False)

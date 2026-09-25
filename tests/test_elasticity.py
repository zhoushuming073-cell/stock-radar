"""Known-value and causal checks for the Elasticity inputs."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from radar.features.elasticity import ElasticityConfig, compute_elasticity_inputs


def _series(length: int = 230) -> tuple[pd.DataFrame, pd.Series, pd.Series]:
    dates = pd.bdate_range("2024-01-01", periods=length)
    market_return = np.tile([0.012, -0.008, 0.006, -0.004, 0.003], length // 5 + 1)[:length]
    spy = pd.Series(100 * np.cumprod(1 + market_return), index=dates)
    stock_close = pd.Series(50 * np.cumprod(1 + 2 * market_return), index=dates)
    bars = pd.DataFrame({"close": stock_close, "high": stock_close * 1.01}, index=dates)
    return bars, spy, spy.copy()


def test_beta_two_and_nearly_zero_idiosyncratic_volatility() -> None:
    bars, spy, qqq = _series()
    result = compute_elasticity_inputs(bars, spy, qqq)
    assert result["beta_spy_60"].iloc[-1] == pytest.approx(2, rel=1e-10)
    assert result["beta_qqq_126"].iloc[-1] == pytest.approx(2, rel=1e-10)
    assert result["idio_vol_spy_60"].iloc[-1] < 1e-6


def test_missing_stock_day_is_not_a_fabricated_daily_return() -> None:
    bars, spy, qqq = _series()
    missing_date = bars.index[-20]
    bars = bars.drop(index=missing_date)
    strict = ElasticityConfig(beta_min_60=60, beta_min_126=126)
    result = compute_elasticity_inputs(bars, spy, qqq, strict)
    assert pd.isna(result.loc[spy.index[-1], "beta_spy_60"])


def test_future_extremes_cannot_rewrite_past_inputs() -> None:
    bars, spy, qqq = _series(210)
    prior = compute_elasticity_inputs(bars, spy, qqq)
    future_dates = pd.bdate_range(bars.index[-1] + pd.Timedelta(days=1), periods=5)
    future_bars = pd.DataFrame({"close": [300, 3, 500, 2, 600], "high": [350, 4, 550, 3, 650]}, index=future_dates)
    extended_bars = pd.concat([bars, future_bars])
    extended_spy = pd.concat([spy, pd.Series([110, 111, 109, 112, 113], index=future_dates)])
    extended_qqq = pd.concat([qqq, pd.Series([105, 106, 104, 107, 108], index=future_dates)])
    after = compute_elasticity_inputs(extended_bars, extended_spy, extended_qqq)
    pd.testing.assert_frame_equal(prior, after.loc[prior.index], check_exact=True)

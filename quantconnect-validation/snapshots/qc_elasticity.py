"""Causal, per-symbol Elasticity inputs; cross-sectional ranking is a later step.

Pandas supplies rolling statistics. The only future-looking calculation below
creates historical five-session outcomes; shifting them by five sessions makes a
window available only after its last day has closed.
"""
from __future__ import annotations
from dataclasses import dataclass
import numpy as np
import pandas as pd

@dataclass(frozen=True)
class ElasticityConfig:
    beta_min_60: int = 50
    beta_min_126: int = 105
    history_window: int = 126
    history_min: int = 40
    burst_quantile: float = 0.75
    hit_5_weight: float = 0.7
    hit_10_weight: float = 0.3
    variance_floor: float = 1e-12

    def __post_init__(self) -> None:
        if not (1 <= self.beta_min_60 <= 60 and 1 <= self.beta_min_126 <= 126):
            raise ValueError('beta minimum observations must fit their windows')
        if not 1 <= self.history_min <= self.history_window:
            raise ValueError('history minimum must fit its window')
        if not 0 < self.burst_quantile < 1:
            raise ValueError('burst quantile must be between zero and one')
        if not np.isclose(self.hit_5_weight + self.hit_10_weight, 1):
            raise ValueError('hit frequency weights must sum to one')

def _market_model(stock_return: pd.Series, market_return: pd.Series, window: int, minimum: int, variance_floor: float) -> tuple[pd.Series, pd.Series]:
    """Rolling OLS slope and residual standard deviation on paired observations."""
    stock = stock_return.where(market_return.notna())
    market = market_return.where(stock_return.notna())
    stock_roll = stock.rolling(window, min_periods=minimum)
    market_roll = market.rolling(window, min_periods=minimum)
    market_var = market_roll.var(ddof=1)
    covariance = stock_roll.cov(market)
    valid_var = market_var.where(market_var > variance_floor)
    beta = covariance / valid_var
    residual_var = (stock_roll.var(ddof=1) - covariance.pow(2) / valid_var).clip(lower=0)
    idio_vol = np.sqrt(residual_var) * np.sqrt(252)
    return (beta, idio_vol)

def compute_elasticity_inputs(bars: pd.DataFrame, spy_close: pd.Series, qqq_close: pd.Series, config: ElasticityConfig=ElasticityConfig()) -> pd.DataFrame:
    """Return inputs on the original bar dates, with missing history as NaN.

    All three close series use market-session dates as their index. The SPY index
    defines the session calendar. A missing stock or benchmark day is never
    filled, so a multi-session jump cannot masquerade as a one-day return.
    """
    if bars.index.has_duplicates or not bars.index.is_monotonic_increasing:
        raise ValueError('bars must have unique, ascending session dates')
    if spy_close.index.has_duplicates or not spy_close.index.is_monotonic_increasing:
        raise ValueError('SPY must have unique, ascending session dates')
    if qqq_close.index.has_duplicates or not qqq_close.index.is_monotonic_increasing:
        raise ValueError('QQQ must have unique, ascending session dates')
    if not bars.index.isin(spy_close.index).all():
        raise ValueError('stock bars contain dates absent from the SPY session calendar')
    sessions = spy_close.index
    close = bars['close'].reindex(sessions).astype(float)
    high = bars['high'].reindex(sessions).astype(float)
    stock_return = close.pct_change(fill_method=None)
    spy_return = spy_close.astype(float).pct_change(fill_method=None)
    qqq_return = qqq_close.reindex(sessions).astype(float).pct_change(fill_method=None)
    result = pd.DataFrame(index=sessions)
    for name, market_return in (('spy', spy_return), ('qqq', qqq_return)):
        for window, minimum in ((60, config.beta_min_60), (126, config.beta_min_126)):
            beta, idio = _market_model(stock_return, market_return, window, minimum, config.variance_floor)
            result[f'beta_{name}_{window}'] = beta
            if window == 60:
                result[f'idio_vol_{name}_60'] = idio
    future_highs = pd.concat([high.shift(-step) for step in range(1, 6)], axis=1)
    completed_excursion = (future_highs.max(axis=1).where(future_highs.notna().all(axis=1)) / close - 1).shift(5)
    trailing = completed_excursion.rolling(config.history_window, min_periods=config.history_min)
    result['burst_p75_5d'] = trailing.quantile(config.burst_quantile)
    result['hit_5_rate'] = completed_excursion.ge(0.05).where(completed_excursion.notna()).rolling(config.history_window, min_periods=config.history_min).mean()
    result['hit_10_rate'] = completed_excursion.ge(0.1).where(completed_excursion.notna()).rolling(config.history_window, min_periods=config.history_min).mean()
    result['elasticity_beta_raw'] = result['beta_spy_60'].abs()
    result['elasticity_idio_raw'] = result['idio_vol_spy_60']
    result['elasticity_burst_raw'] = result['burst_p75_5d']
    result['elasticity_hit_raw'] = config.hit_5_weight * result['hit_5_rate'] + config.hit_10_weight * result['hit_10_rate']
    return result.loc[bars.index]

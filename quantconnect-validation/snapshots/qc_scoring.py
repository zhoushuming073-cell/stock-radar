"""Same-date cross-sectional Elasticity normalization and a separate trade gate."""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path
import numpy as np
import pandas as pd
import yaml
COMPONENTS = {'beta': 'elasticity_beta_raw', 'atr': 'elasticity_atr_raw', 'idio': 'elasticity_idio_raw', 'burst': 'elasticity_burst_raw', 'hit_rate': 'elasticity_hit_raw'}
COMPONENT_NAMES = {'hit_rate': 'hit', 'beta': 'beta', 'atr': 'atr', 'idio': 'idio', 'burst': 'burst'}

@dataclass(frozen=True)
class ResearchConfig:
    weights: dict[str, float]
    min_price: float
    min_avg_dollar_volume_20: float
    min_history_sessions: int

def load_research_config(path: Path) -> ResearchConfig:
    cfg = yaml.safe_load(path.read_text(encoding='utf-8'))
    weights = cfg['elasticity']['weights']
    if set(weights) != set(COMPONENTS) or not np.isclose(sum(weights.values()), 1):
        raise ValueError('Elasticity weights must define five components and sum to one')
    gate = cfg['tradability']
    return ResearchConfig(weights, float(gate['min_price']), float(gate['min_avg_dollar_volume_20']), int(gate['min_history_sessions']))

def score_elasticity(features: pd.DataFrame, config: ResearchConfig) -> pd.DataFrame:
    """Score rows independently within each date; retain unknown scores as NaN."""
    needed = {'date', *COMPONENTS.values()}
    if not needed.issubset(features):
        raise ValueError(f'missing feature columns: {sorted(needed - set(features))}')
    result = features.copy()
    components = []
    for name, raw in COMPONENTS.items():
        column = f'elasticity_{COMPONENT_NAMES[name]}_component'
        result[column] = result.groupby('date', sort=False)[raw].rank(pct=True) * 100
        components.append(column)
    result['elasticity_score'] = sum((config.weights[name] * result[f'elasticity_{COMPONENT_NAMES[name]}_component'] for name in COMPONENTS))
    result.loc[result[components].isna().any(axis=1), 'elasticity_score'] = np.nan
    return result

def tradability_gate(features: pd.DataFrame, config: ResearchConfig) -> pd.Series:
    """Historical OHLCV-only eligibility at the signal close.

    The current asset snapshot defines a survivor cohort elsewhere; its mutable
    tradable and exchange fields must not be projected onto historical dates.
    """
    needed = {'close', 'avg_dollar_volume_20', 'history_sessions'}
    if not needed.issubset(features):
        raise ValueError(f'missing gate columns: {sorted(needed - set(features))}')
    return (features['close'].ge(config.min_price) & features['avg_dollar_volume_20'].ge(config.min_avg_dollar_volume_20) & features['history_sessions'].ge(config.min_history_sessions)).fillna(False)

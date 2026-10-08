import pandas as pd
from qc_base_features import compute_base_features
from qc_elasticity import compute_elasticity_inputs
from qc_scoring import tradability_gate
from qc_strategy_features import compute_strategy2_features
def causal_identity_features(bars, spy, qqq, ecfg, cfg, *, actions=None, security_id=None):
    """Unchanged feature formula, recomputed at each *known effective* raw split.

    A future split cannot change any earlier row. Raw execution bars stay raw;
    only historical windows for features after an effective split are rescaled.
    Dividend adjustment is not part of this feature convention.
    """
    from qc_split import split_adjust
    actions = [a for a in actions or [] if a['security_id'] == security_id and a['event_type'] in {'split', 'reverse_split'}]
    boundaries = sorted({pd.Timestamp(a['effective_date']) for a in actions if bars.index.min() <= pd.Timestamp(a['effective_date']) <= bars.index.max()})
    segments = [bars.index.min(), *boundaries, bars.index.max() + pd.Timedelta(days=1)]
    parts = []
    for first, last in zip(segments, segments[1:]):
        through = bars.loc[bars.index < last].copy()
        if actions:
            raw = through.reset_index(names='date')
            raw['security_id'] = security_id
            through = split_adjust(raw, actions, str(first.date())).set_index('date')[bars.columns]
        feature = pd.concat([compute_base_features(through), compute_elasticity_inputs(through, spy, qqq, ecfg), compute_strategy2_features(through, spy, qqq)], axis=1)
        feature['elasticity_atr_raw'] = feature.atr_pct_20
        feature['tradability_pass'] = tradability_gate(pd.DataFrame({'close': through.close, 'avg_dollar_volume_20': feature.avg_dollar_volume_20, 'history_sessions': through.close.notna().cumsum()}, index=through.index), cfg)
        parts.append(feature.loc[(feature.index >= first) & (feature.index < last)])
    return pd.concat(parts).reindex(bars.index)

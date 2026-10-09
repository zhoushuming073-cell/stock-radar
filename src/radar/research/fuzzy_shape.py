"""Independent Q1 fuzzy-shape-v1 kernel; parity locked to the accepted v1.

Original Vision namespace stays byte-identical for frozen artifact verification.
No Vision, Human, outcomes or market IO dependencies.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

DIMENSIONS = ('strength', 'pullback', 'exhaustion', 'support_proxy', 'turning', 'entry_location')


def ramp(x, bounds):
    lo, hi = bounds
    return float(np.clip((x - lo) / (hi - lo), 0, 1))


def trapezoid(x, bounds):
    a, b, c, d = bounds
    return min(ramp(x, (a, b)), 1 - ramp(x, (c, d)))


def array_features(values, config):
    """Numeric kernel; the caller must supply a frozen, prefix-only safe window."""
    a = np.asarray(values, dtype=float)
    if a.ndim != 2 or a.shape[1] != 5 or len(a) not in (60, 126):
        raise ValueError('60/126 canonical OHLCV required')
    if (not np.isfinite(a).all() or (a[:, :4] <= 0).any() or (a[:, 4] < 0).any()
            or (a[:, 1] < a[:, [0, 2, 3]].max(axis=1)).any()
            or (a[:, 2] > a[:, [0, 3]].min(axis=1)).any()):
        raise ValueError('invalid OHLCV')
    o, h, l, c, v = a.T
    r = c[1:] / c[:-1] - 1
    eps = 1e-12
    peak = int(np.argmax(h[:-5]))
    trough_before = float(l[:peak + 1].min())
    rise = h[peak] / trough_before - 1
    depth = 1 - c[-1] / h[peak]
    duration = len(a) - 1 - peak
    low20 = float(l[-20:].min())
    body = np.maximum(o - c, 0) / o
    clv = (c - l) / np.maximum(h - l, eps)
    lower_wick = (np.minimum(c, o) - l) / np.maximum(h - l, eps)
    neg5 = float(np.maximum(-r[-5:], 0).mean())
    neg_prev = float(np.maximum(-r[-15:-5], 0).mean())
    body_ratio = float(body[-5:].mean() / max(body[-15:-5].mean(), eps))
    vol_ratio = float(np.std(r[-5:]) / max(np.std(r[-20:-5]), eps))
    low_change = float(l[-5:].min() / l[-15:-5].min() - 1)
    down = c[-20:] < o[-20:]
    up = ~down
    recent_down = c[-5:] < o[-5:]
    down_v = float(v[-20:][down].mean()) if down.any() else float(v[-20:].mean())
    up_v = float(v[-20:][up].mean()) if up.any() else 0.0
    recent_down_v = float(v[-5:][recent_down].mean()) if recent_down.any() else 0.0
    rebound = c[-1] / low20 - 1
    ma_distance = c[-1] / c[-10:].mean() - 1
    ret5 = c[-1] / c[-6] - 1
    positive = np.maximum(r, 0)
    concentration = float(np.sort(positive)[-3:].sum() / max(positive.sum(), eps))
    ret = {f'return_{n}': float(c[-1] / c[max(0, len(c)-1-n)] - 1) for n in (5, 20, 60, 125)}
    f = dict(ret, prior_runup=rise, high_position=c[-1]/h.max(), low_position=c[-1]/l.min()-1,
             positive_day_concentration=concentration, pullback_depth=depth, pullback_sessions=float(duration),
             downside_acceleration=neg5/max(neg_prev, eps), red_body_ratio=body_ratio,
             volatility_ratio=vol_ratio, recent_low_change=low_change,
             down_volume_ratio=recent_down_v/max(down_v, eps), up_down_volume_ratio=up_v/max(down_v, eps),
             rejection_wick=float(lower_wick[-5:].mean()), close_location=float(clv[-5:].mean()),
             green_fraction=float((c[-5:]>o[-5:]).mean()), local_breakout=c[-1]/h[-11:-1].max()-1,
             last_day_return=float(r[-1]), rebound_from_low=rebound, ma10_distance=ma_distance,
             recent_volume_ratio=float(v[-1]/max(v[-20:].mean(),eps)), recent_return_5=ret5)
    s = config['scores']
    scores = {}
    scores['strength'] = ramp(rise, s['strength_rise']) * (1 - s['concentration_penalty']*ramp(concentration, s['concentration']))
    scores['pullback'] = (trapezoid(depth, s['pullback_depth']) * s['pullback_depth_weight']
                           + trapezoid(duration, s['pullback_duration'])*(1-s['pullback_depth_weight'])) * (1-s['breakdown_penalty']*ramp(-low_change,s['low_breakdown']))
    scores['exhaustion'] = np.average([1-ramp(f['downside_acceleration'],s['exhaustion_ratio']),
                                  1-ramp(body_ratio,s['exhaustion_ratio']), 1-ramp(vol_ratio,s['exhaustion_ratio']),
                                  ramp(low_change,s['low_stabilization'])],weights=s['exhaustion_weights'])
    scores['support_proxy'] = np.average([1-ramp(f['down_volume_ratio'],s['down_volume']),
                                     ramp(f['up_down_volume_ratio'],s['up_down_volume']),
                                     ramp(f['rejection_wick'],s['wick']), ramp(f['close_location'],s['support_close_location'])],weights=s['support_weights'])
    scores['turning'] = np.average([ramp(f['green_fraction'],s['green_fraction']), ramp(f['close_location'],s['turning_close_location']),
                               ramp(ret5,s['turning_return']), ramp(f['local_breakout'],s['local_breakout'])],weights=s['turning_weights'])
    extension = np.average([ramp(r[-1],s['last_day_extension']),ramp(rebound,s['rebound_extension']),
                         ramp(ma_distance,s['ma_extension']),ramp(ret5,s['five_day_extension'])],weights=s['extension_weights'])
    scores['entry_location'] = 1-extension
    f.update({f'score_{k}':float(x*100) for k,x in scores.items()})
    f['extension_score'] = float(extension*100)
    w=s['weights']
    f['quant_score'] = float(sum(scores[k]*w[k] for k in DIMENSIONS)*100)
    f['shape_score'] = float(sum(scores[k]*w[k] for k in DIMENSIONS[:-1])/(1-w['entry_location'])*100)
    if not all(np.isfinite(list(f.values()))):
        raise ValueError('nonfinite quant features')
    return f


def features_at(frame, decision_date, config):
    """Prefix-only public kernel, deliberately ignoring later rows entirely."""
    if set(frame) != {'date','open','high','low','close','volume'}:
        raise ValueError('only canonical OHLCV allowed')
    dates=pd.to_datetime(frame.date)
    f=frame.loc[dates <= pd.Timestamp(decision_date)]
    if f.empty or not f.date.is_monotonic_increasing or f.date.duplicated().any():
        raise ValueError('ordered unique prefix required')
    if pd.Timestamp(f.date.iloc[-1]) != pd.Timestamp(decision_date):
        raise ValueError('missing decision session')
    return array_features(f[['open','high','low','close','volume']].to_numpy(),config)


def stratum(f, config):
    s=config['scores']
    if f['shape_score'] >= s['conflict_shape_score'] and f['extension_score'] >= s['conflict_extension_score']:
        return 'conflict'
    if f['quant_score'] >= s['high_score']: return 'high'
    if f['quant_score'] >= s['medium_score']: return 'medium'
    if f['quant_score'] >= s['boundary_score']: return 'boundary'
    return 'control'

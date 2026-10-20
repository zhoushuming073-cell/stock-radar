"""Multi-scale as-of-T OHLCV and deterministic numeric model inputs."""
import hashlib
import json
import numpy as np
import pandas as pd
from .history import CHANNELS

VERSION = 'box-numeric-ohlcv-v2-42d-52w-48m'
LENGTHS = {'daily': 42, 'weekly': 52, 'monthly': 48}


def digest(value):
    return hashlib.sha256(value).hexdigest()


def canonical(frame):
    return json.dumps([[str(r.date.date()), *[float(getattr(r, k)) for k in CHANNELS]]
                       for r in frame.itertuples(index=False)], separators=(',', ':'), allow_nan=False).encode()


def scales(history, decision_date):
    day = pd.Timestamp(decision_date).normalize()
    source = history.loc[pd.to_datetime(history.date).le(day), ['date', *CHANNELS]].copy()
    source['date'] = pd.to_datetime(source.date)
    if source.empty or source.date.iloc[-1] != day or source.date.duplicated().any():
        raise ValueError('history must end at unique decision date')
    if source[list(CHANNELS)].isna().any().any() or source[['open','high','low','close']].le(0).any().any():
        raise ValueError('invalid numeric history')
    indexed = source.set_index('date')
    result = {'daily': source}
    for name, freq in [('weekly', 'W-FRI'), ('monthly', 'ME')]:
        f = indexed.resample(freq).agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna().reset_index()
        # Label the partial final bar by its actual last observed session, not Friday/month-end.
        actual = indexed['close'].resample(freq).apply(lambda x: x.index.max() if len(x) else pd.NaT).dropna()
        f['date'] = pd.to_datetime(actual.to_numpy())
        if f.date.iloc[-1] != day:
            raise ValueError('partial period incorrectly completed')
        result[name] = f
    return result


def numeric_bundle(history, decision_date):
    raw = scales(history, decision_date)
    anchor = float(raw['daily'].close.iloc[-1])
    out = {'version': VERSION, 'decision_date': str(pd.Timestamp(decision_date).date()),
           'normalization': 'log(OHLC/T_close); log1p(volume)/log1p(median_past_volume)',
           'anchor': anchor, 'scales': {}}
    for name, frame in raw.items():
        frame = frame.tail(LENGTHS[name]).reset_index(drop=True)
        values = frame[list(CHANNELS)].to_numpy(dtype=np.float64)
        median = max(float(np.median(values[:,4])), 1.0)
        normalized = np.column_stack([np.log(values[:,:4] / anchor),
                                      np.log1p(values[:,4]) / np.log1p(median)]).astype('<f4')
        if not np.isfinite(normalized).all():
            raise ValueError('nonfinite tensor')
        out['scales'][name] = {'raw': frame, 'tensor': normalized,
                               'available': len(frame) == LENGTHS[name],
                               'raw_hash': digest(canonical(frame)),
                               'tensor_hash': digest(normalized.tobytes()),
                               'length': len(frame)}
    return out

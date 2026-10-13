"""High-recall numeric retrieval only; these scores are never human truth."""
import numpy as np
import pandas as pd
from .base import CandidateResult

VERSION = 'loose-box-v1'


def evaluate(history: pd.DataFrame, cfg: dict) -> CandidateResult:
    required = {'date','open','high','low','close','volume'}
    if set(history) != required or len(history) < 126:
        raise ValueError('candidate plugin requires a bounded 126+ bar numeric prefix')
    if pd.to_datetime(history.date).is_monotonic_increasing is False:
        raise ValueError('ordered past-only input required')
    x = history.tail(int(cfg['sessions']))
    close = x.close.to_numpy(dtype=float)
    low = x.low.to_numpy(dtype=float)
    high = x.high.to_numpy(dtype=float)
    floor, ceiling = np.quantile(low, .12), np.quantile(high, .88)
    width = (ceiling-floor)/max(float(np.median(close)), 1e-12)
    position = (close[-1]-floor)/max(ceiling-floor, 1e-12)
    occupancy = float(np.mean((close >= floor*.97) & (close <= ceiling*1.03)))
    steps = np.diff(close)
    smooth = np.convolve(steps, np.ones(5)/5, mode='valid')
    turns = int(np.sum(np.sign(smooth[1:]) != np.sign(smooth[:-1])))
    drift = float(close[-1]/close[0]-1)
    undercut = float(max(0, (floor-min(low[-15:]))/max(floor,1e-12)))
    rules = {'width': width >= float(cfg['min_width']),
             'occupancy': occupancy >= float(cfg['min_occupancy']),
             'turns': turns >= int(cfg['min_turns']),
             'drift': abs(drift) <= float(cfg['max_abs_drift']),
             'breakdown': position >= float(cfg['min_position'])}
    score = float(np.clip(.30*occupancy + .25*min(turns/10,1) +
                          .20*min(width/.30,1) + .15*(1-min(abs(drift),1)) +
                          .10*(1-min(undercut/.15,1)),0,1))
    diagnostics = {'occupancy':occupancy,'turns':turns,'width':float(width),
                   'position':float(position),'drift':drift,'undercut':undercut}
    return CandidateResult(all(rules.values()),score,diagnostics,
                           tuple(key for key, valid in rules.items() if not valid))

import math
import pandas as pd
def split_adjust(raw: pd.DataFrame, actions: list[dict], as_of: str) -> pd.DataFrame:
    """Causal split-only feature prices; volume scales reciprocally to prices.

    Only actions effective by as_of enter features. Execution consumes raw bars,
    letting native LEAN adjust holdings once. Dividend-adjusted inputs rejected.
    """
    frame = raw.copy()
    frame['date'] = pd.to_datetime(frame['date'])
    for action in actions:
        if action['event_type'] not in {'split', 'reverse_split'} or action['effective_date'] > as_of:
            continue
        if action['handling_mode'] != 'native_raw_split' or action['confidence'] != 'verified':
            raise ValueError('unverified split factor')
        ratio = float(action['ratio'])
        if not math.isfinite(ratio) or ratio <= 0:
            raise ValueError('invalid split ratio')
        mask = frame.security_id.eq(action['security_id']) & frame.date.lt(pd.Timestamp(action['effective_date']))
        for name in ('open', 'high', 'low', 'close'):
            frame.loc[mask, name] = frame.loc[mask, name].astype(float) / ratio
        frame.loc[mask, 'volume'] = frame.loc[mask, 'volume'].astype(float) * ratio
    return frame

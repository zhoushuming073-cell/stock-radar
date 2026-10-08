"""QC-only data access. Local membership/identity never constructs QC Core."""
from AlgorithmImports import *
from datetime import datetime, timedelta
import pandas as pd
from qc_protocol import normalize_cik, normalize_class


def historical_population(algorithm, universe, day):
    start = datetime.fromisoformat(day)
    # Fundamental objects at the historical timestamp: do not call current Fundamentals().
    series = algorithm.history(universe, start, start + timedelta(days=1))
    objects = []
    for key, group in series.items():
        stamp = key[-1] if isinstance(key, tuple) else key
        if str(pd.Timestamp(stamp).date()) != day:
            raise ValueError('Unexpected fundamental timestamp; no date backfill')
        objects.extend(group)
    if not objects:
        raise ValueError('Historical universe inaccessible; never substitute current symbols')
    seen, result = set(), []
    for f in objects:
        sid = str(f.symbol.id)
        if sid in seen:
            raise ValueError('Duplicate historical SID')
        seen.add(sid)
        ref = f.security_reference
        kind = str(ref.security_type)
        ipo = ref.ipo_date
        listing = str(ipo.date()) if ipo.year > 1900 else None
        result.append({'symbol_object': f.symbol, 'sid': sid, 'ticker': f.symbol.value,
            'as_of': day, 'cik': normalize_cik(f.company_reference.cik),
            'class': normalize_class(ref.share_class_description),
            'security_type': 'common' if kind == 'ST00000001' and not ref.is_depositary_receipt
                             else ('unknown' if not kind else 'other'),
            'listing_date': listing})
    return result


def raw_frames(algorithm, symbols, first, end):
    """Typed history retains immutable Symbol.ID; no DataFrame ticker-string join."""
    frames = {str(s.id): [] for s in symbols}
    for offset in range(0, len(symbols), 128):
        batch = symbols[offset:offset + 128]
        history = algorithm.history[TradeBar](batch, datetime.fromisoformat(first), end,
            Resolution.DAILY, fill_forward=False, data_normalization_mode=DataNormalizationMode.RAW)
        for sliced in history:
            for symbol in batch:
                if not sliced.contains_key(symbol):
                    continue
                bar = sliced[symbol]
                sid = str(symbol.id)
                if sid not in frames or bar.is_fill_forward:
                    raise ValueError('Foreign SID/fill-forward in raw history')
                # daily_precise_end_time: bar closes on its actual session date.
                date = str(bar.end_time.date())
                if bar.end_time.hour not in {13, 16} or bar.end_time > end:
                    raise ValueError('Raw daily timestamp semantics failed; run smoke first')
                frames[sid].append({'date': date, 'open': float(bar.open), 'high': float(bar.high),
                    'low': float(bar.low), 'close': float(bar.close), 'volume': float(bar.volume)})
    for sid, rows in frames.items():
        frame = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        if frame.date.duplicated().any():
            raise ValueError('Duplicate raw daily sessions')
        frame['date'] = pd.to_datetime(frame.date)
        frames[sid] = frame.set_index('date').sort_index()
    return frames


def split_actions(algorithm, symbol, first, end):
    result = []
    for event in algorithm.history[Split](symbol, datetime.fromisoformat(first), end):
        if event.type != SplitType.SPLIT_OCCURRED:
            continue
        if event.end_time > end or float(event.split_factor) <= 0:
            raise ValueError('Invalid/future split event')
        result.append({'security_id': str(symbol.id), 'effective_date': str(event.end_time.date()),
            'event_type': 'split', 'confidence': 'verified', 'handling_mode': 'native_raw_split',
            'ratio': 1 / float(event.split_factor)})
    return result

"""Read-only, dated Research Infrastructure v1 history capability."""
from pathlib import Path
import pandas as pd
import numpy as np
from radar.research.infrastructure import shape_research_universe_v1

CHANNELS = ('open', 'high', 'low', 'close', 'volume')


class BoxHistory:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.api = shape_research_universe_v1(self.root)

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.api.__exit__(*args)

    @property
    def semantic_hash(self):
        return self.api.fingerprint

    def history(self, security_id, decision_date, max_sessions=1100):
        """Return a defensive copy of one trusted contiguous prefix through T."""
        day = pd.Timestamp(decision_date).normalize()
        if day >= pd.Timestamp(self.api.profile['semantics']['fresh_start']):
            raise ValueError('Fresh decisions are outside Box Labeling v1')
        if not isinstance(max_sessions, int) or not 126 <= max_sessions <= 1100:
            raise ValueError('max_sessions must be 126..1100')
        safe = self.api.window(security_id, day, 126, dataset=False)
        series = safe.metadata['series_id']
        bars = self.api.core.connection.execute('''SELECT date,open,high,low,close,volume,
            session_no,shape_research_ready,source,basis FROM shape_price
            WHERE series_id=? AND date<=? ORDER BY date DESC LIMIT ?''',
            [series, day.date(), max_sessions]).df().iloc[::-1].reset_index(drop=True)
        if bars.empty or pd.Timestamp(bars.date.iloc[-1]) != day:
            raise ValueError('decision-date bar unavailable')
        if not bars.source.eq(safe.metadata['source']).all() or not bars.basis.eq(safe.metadata['basis']).all():
            raise ValueError('mixed source or price basis')
        if not bars.shape_research_ready.all():
            raise ValueError('unsafe historical bar')
        gaps = bars.session_no.diff().fillna(1).ne(1)
        if gaps.any():
            bars = bars.iloc[int(np.flatnonzero(gaps.to_numpy())[-1]):].reset_index(drop=True)
        if len(bars) < 126 or pd.to_datetime(bars.date).gt(day).any():
            raise ValueError('incomplete causal 126-session history')
        result = bars[['date', *CHANNELS]].copy()
        result['date'] = pd.to_datetime(result.date)
        result.attrs.update(security_id=security_id, decision_date=str(day.date()),
                            backend='research_infrastructure_v1', semantic_hash=self.semantic_hash,
                            source=safe.metadata['source'], basis=safe.metadata['basis'])
        return result

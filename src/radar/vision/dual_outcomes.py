"""Separate, bounded future-reader and Y generator. Never called by Q or Stage A."""
from hashlib import sha256
import json
import math
import pandas as pd
from .dual_contracts import FutureOutcome

def outcome(bars,reference,source_hash,flags=(),*,prior_low=None):
    if len(bars)!=10:raise ValueError('ten exchange sessions required')
    flags=list(flags)
    for b in bars:
        if b is not None and (set(b)!={'open','high','low','close','volume'} or any(not math.isfinite(v) for v in b.values()) or min(b[k] for k in ('open','high','low','close'))<=0 or b['volume']<0 or b['high']<max(b['open'],b['close'],b['low']) or b['low']>min(b['open'],b['close'])):raise ValueError('invalid future OHLCV')
    entry=bars[0]['open'] if bars[0] is not None and bars[0]['volume']>0 and not flags else None
    status='available';event='neither_hit';day=None;conservative=None
    if entry is None:status='unavailable';event='not_evaluable'
    elif any(b is None or b['volume']==0 for b in bars):status='censored';event='not_evaluable';flags.append('missing_or_nontrading_session')
    returns={str(n):None for n in (1,3,5,10)};mfe=mae=new_low=None
    if status=='available':
        returns={str(n):bars[n-1]['close']/entry-1 for n in (1,3,5,10)}
        mfe=max(b['high']/entry-1 for b in bars);mae=min(b['low']/entry-1 for b in bars)
        new_low=any(b['low']<prior_low for b in bars) if prior_low is not None else None
        for i,b in enumerate(bars,1):
            if i>1 and b['open']>=entry*1.05:event='target_first';day=i;flags.append('opening_gap_target');break
            if i>1 and b['open']<=entry*.97:event='adverse_first';day=i;flags.append('opening_gap_adverse');break
            target=b['high']>=entry*1.05;adverse=b['low']<=entry*.97
            if target and adverse:status='ambiguous';event='both_same_bar';day=i;conservative='adverse_first';break
            if target or adverse:event='target_first' if target else 'adverse_first';day=i;break
    if bars[0] is not None and reference>0 and abs(bars[0]['open']/reference-1)>=.05:flags.append('entry_gap_from_T_close')
    return FutureOutcome(version='y-future-v3',horizon=10,entry_reference='T+1 vendor-basis open; relative research proxy',target=.05,adverse=-.03,fee_bps=0,slippage_bps=0,status=status,event=event,event_day=day,entry_open=entry,returns=returns,mfe=mfe,mae=mae,new_low=new_low,conservative_event=conservative,flags=sorted(set(flags)),source_hash=source_hash).model_dump()

def read_future(db,metadata):
    decision=pd.Timestamp(metadata['decision_date']);split=metadata['split_assignment']
    if split not in ('train','validation'):raise ValueError('no Test/Fresh outcomes authorized')
    # The same source series selected at T is pinned; never choose via future completeness.
    calendar=db.core.connection.execute('SELECT date FROM sessions WHERE date>? ORDER BY date LIMIT 10',[decision.date()]).df().date.tolist()
    if len(calendar)!=10:raise ValueError('insufficient frozen calendar')
    end=pd.Timestamp(db.profile['semantics']['frozen_splits'][split][1]);flags=[]
    if pd.Timestamp(calendar[-1])>end:
        # Do not even query rows outside the allowed split/embargo.
        bars=[None]*10;flags=['horizon_crosses_split'];source=sha256(b'blocked split horizon').hexdigest();return bars,flags,source
    rows=db.core.connection.execute('SELECT * FROM shape_price WHERE series_id=? AND date>? AND date<=? ORDER BY date',[metadata['series_id'],decision.date(),calendar[-1]]).df()
    if rows.date.duplicated().any():raise ValueError('ambiguous future series')
    actions=db.core.connection.execute('SELECT date,factor FROM split_action WHERE security_id=? AND date>? AND date<=?',[metadata['security_id'],decision.date(),calendar[-1]]).df()
    if not actions.empty:flags.append('corporate_split_horizon_unsupported')
    bydate={pd.Timestamp(row.date):row for row in rows.itertuples()};bars=[]
    for day in calendar:
        row=bydate.get(pd.Timestamp(day))
        trusted=row is not None and row.shape_research_ready and row.membership_status in ('confirmed_member','probable_member') and row.basis==metadata['basis'] and row.source==metadata['source']
        bars.append({k:float(getattr(row,k)) for k in ('open','high','low','close','volume')} if trusted else None)
    # Hash actual per-session source identity/quality in private provenance.
    source=sha256(rows.to_json(orient='records',date_format='iso').encode()).hexdigest()
    return bars,flags,source

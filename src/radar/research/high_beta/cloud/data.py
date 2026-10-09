"""QC-native evidence and causal price/volume transport, not selector formulas."""
from dataclasses import dataclass, asdict
import math
import pandas as pd


@dataclass(frozen=True)
class QcEvidence:
    identity_trusted: bool
    common_stock: bool
    split_events_verified: bool
    scope: str = 'qc_cloud_exploratory'
    source: str = 'quantconnect'
    feed: str = 'qc_native'
    adjustment: str = 'split'
    joint_price_volume_adjustment: bool = True
    historical_certified: bool = False

    def refusal(self):
        if not self.identity_trusted:return 'qc_historical_identity_unknown'
        if not self.common_stock:return 'qc_instrument_not_common'
        if not self.split_events_verified:return 'qc_causal_split_evidence_missing'
        if (self.scope,self.source,self.feed,self.adjustment)!=('qc_cloud_exploratory','quantconnect','qc_native','split'):
            return 'qc_domain_mismatch'
        if not self.joint_price_volume_adjustment:return 'qc_joint_basis_missing'
        if self.historical_certified:return 'qc_cannot_assert_local_certification'
        return None

    def model_dump(self):return asdict(self)


class Candidate:
    """Cloud-only serialization transport; computed fields validated by digest.

    Avoid requiring a specific Pydantic build inside the free Cloud environment.
    This does not replace Stock Radar's original Pydantic contract.
    """
    def __init__(self,**values):self.__dict__.update(values)
    def model_copy(self,update):return Candidate(**{**self.__dict__,**update})
    def model_dump(self,**_):return dict(self.__dict__)


def causal_split_window(raw,events,asof):
    """Use only split events effective <=T; adjust both price and volume."""
    x=raw.copy();x['date']=pd.to_datetime(x.date)
    t=pd.Timestamp(asof);x=x.loc[x.date<=t].sort_values('date').reset_index(drop=True)
    if x.date.duplicated().any():raise ValueError('duplicate QC raw sessions')
    x[['open','high','low','close','volume']]=x[['open','high','low','close','volume']].astype(float)
    seen=set()
    for event in sorted(events,key=lambda e:e['effective_date']):
        day=pd.Timestamp(event['effective_date'])
        if day>t:continue
        if event['confidence']!='verified' or event['event_type']!='split':raise ValueError('unverified QC action')
        if day in seen:raise ValueError('duplicate QC split date')
        seen.add(day);ratio=float(event['ratio'])
        if not math.isfinite(ratio) or ratio<=0:raise ValueError('invalid QC split ratio')
        mask=x.date<day
        x.loc[mask,['open','high','low','close']]/=ratio
        x.loc[mask,'volume']*=ratio
    # Fractional adjusted volume is NOT silently rounded. Original gate decides.
    return x


def common_identity(f,asof):
    ref=f.security_reference;kind=str(ref.security_type)
    ipo=ref.ipo_date
    if not f.has_fundamental_data or not kind:return False
    if kind!='ST00000001' or ref.is_depositary_receipt:return False
    if ipo.year<=1900 or ipo.date()>pd.Timestamp(asof).date():return False
    return bool(str(f.symbol.id))


def complete_amount(raw,days):
    """Safe first gate: RAW price×RAW volume is invariant to joint splits."""
    x=raw.set_index('date').reindex(pd.DatetimeIndex(days))
    if x[['close','volume']].isna().any().any():return None
    if (x.close<=0).any() or (x.volume<0).any():return None
    amount=float((x.close*x.volume).mean())
    return amount if math.isfinite(amount) else None


def history_frames(algorithm,symbols,first,end):
    from AlgorithmImports import TradeBar,Resolution,DataNormalizationMode
    rows={str(s.id):[] for s in symbols}
    for i in range(0,len(symbols),64):
        batch=symbols[i:i+64]
        for sliced in algorithm.history[TradeBar](batch,first,end,Resolution.DAILY,
                fill_forward=False,data_normalization_mode=DataNormalizationMode.RAW):
            for symbol in batch:
                if not sliced.contains_key(symbol):continue
                bar=sliced[symbol]
                sid=str(symbol.id)
                if sid not in rows or bar.is_fill_forward or bar.end_time>end:
                    raise ValueError('foreign/fill-forward/future raw QC bar')
                if bar.end_time.hour not in {13,16}:raise ValueError('QC daily timestamp semantics changed')
                rows[sid].append(dict(date=pd.Timestamp(bar.end_time.date()),open=float(bar.open),
                    high=float(bar.high),low=float(bar.low),close=float(bar.close),volume=float(bar.volume)))
    frames={}
    for sid,values in rows.items():
        x=pd.DataFrame(values,columns=['date','open','high','low','close','volume'])
        if x.date.duplicated().any():raise ValueError('duplicate typed QC SID history')
        frames[sid]=x.sort_values('date').reset_index(drop=True)
        frames[sid]['date']=pd.to_datetime(frames[sid].date)
    return frames


def split_events(algorithm,symbol,first,end):
    from AlgorithmImports import Split,SplitType
    events=[]
    for e in algorithm.history[Split](symbol,first,end):
        if e.type!=SplitType.SPLIT_OCCURRED:continue
        if e.end_time>end or float(e.split_factor)<=0:raise ValueError('future/invalid QC split')
        events.append(dict(effective_date=str(e.end_time.date()),event_type='split',
            confidence='verified',ratio=1/float(e.split_factor)))
    return events


def population(algorithm,universe,asof):
    from datetime import datetime,timedelta
    first=datetime.fromisoformat(asof);end=first+timedelta(days=1)
    if end>algorithm.time:raise ValueError('QC universe request crosses available clock')
    result=[];seen=set();observed=False
    for key,objects in algorithm.history(universe,first,end).items():
        stamp=key[-1] if isinstance(key,tuple) else key
        if str(pd.Timestamp(stamp).date())!=asof:raise ValueError('QC fundamental date backfill')
        observed=True
        for f in objects:
            sid=str(f.symbol.id)
            if sid in seen:raise ValueError('duplicate historical QC SID')
            seen.add(sid)
            if common_identity(f,asof):result.append(f.symbol)
    if not observed:raise ValueError('QC historical universe unavailable; no current ticker fallback')
    return sorted(result,key=lambda s:str(s.id))

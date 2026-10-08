"""Stable lazy entry point for local shape research, frozen data and policy.

Historical strict stores are never opened on import or construction. Only the
Shape core and optional local incremental sidecar are opened on first access.
"""
from hashlib import sha256
import json
from pathlib import Path

import duckdb
import pandas as pd

from radar.pit.shape import ShapeResearchDatabase, ShapeWindow, canonical_hash, normalize_window
from radar.pit.features import file_hash


def semantic_hash(value):
    return sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False).encode()).hexdigest()


def fresh_decision(day,start):
    return pd.Timestamp(day).normalize()>=pd.Timestamp(start).normalize()


def validate_freeze(receipt, start):
    """No automatic backdating: both artifacts and their receipt must predate F.

    Actual file hashes bind parameters/model. This validates a dated receipt,
    not a third-party timestamp authority; no existing receipt is invented.
    """
    if not {'recorded_at','model_frozen_at','parameters_frozen_at','model','parameters'}<=set(receipt):
        raise ValueError('complete dated model/parameter freeze receipt required')
    cutoff=pd.Timestamp(start,tz='America/New_York').tz_convert('UTC')
    for key in ('recorded_at','model_frozen_at','parameters_frozen_at'):
        value=pd.Timestamp(receipt[key])
        if value.tzinfo is None or value.tz_convert('UTC')>=cutoff:
            raise ValueError('model/parameter freeze and receipt must precede Fresh OOS')
    for key in ('model','parameters'):
        item=receipt[key]
        if file_hash(Path(item['path']))!=item['sha256']:
            raise ValueError('frozen model/parameter changed')
    if receipt.get('used_fresh_outcomes_for_tuning',True):
        raise ValueError('Fresh outcomes must not tune configuration')
    return True


def reject_future_benchmark(series,decision):
    if not isinstance(series.index,pd.DatetimeIndex) or series.index.has_duplicates or not series.index.is_monotonic_increasing:
        raise ValueError('ordered unique benchmark dates required')
    if (series.index>pd.Timestamp(decision)).any():raise ValueError('post-decision benchmark input rejected')
    return series


def validate_input(frame, decision):
    allowed={'security_id','date','symbol','open','high','low','close','volume','basis','source','source_hash','membership_status',
             'shape_research_status','shape_research_ready'}
    if set(frame)-allowed:raise ValueError('labels or unapproved metadata must remain outside input')
    if (pd.to_datetime(frame.date)>pd.Timestamp(decision)).any():raise ValueError('future input rejected')


class ResearchInfrastructure:
    """shape_research_universe_v1: default supported-only local research API."""
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.profile=json.loads((self.root/'config/research_infrastructure_v1.json').read_text(encoding='utf-8'))
        if semantic_hash(self.profile['semantics'])!=self.profile['semantic_hash']:raise ValueError('frozen configuration mutated')
        locks=[('src/radar/research/infrastructure.py',self.profile['semantics'].get('research_api_code_sha256')),
               ('config/shape_research_contract_v1.json',self.profile.get('contract_file_sha256')),
               ('config/shape_research_rules.json',self.profile.get('rules_hash'))]
        for path,expected in locks:
            if expected and file_hash(self.root/path)!=expected:raise ValueError('frozen research dependency changed: '+path)
        self.fingerprint=self.profile['semantic_hash']
        self._core=None;self._fresh=None

    @property
    def core(self):
        if self._core is None:
            self._core=ShapeResearchDatabase(self.root/self.profile['core_directory'])
            if self._core.manifest['database_sha256']!=self.profile['semantics']['core_database_sha256']:
                self._core.connection.close();self._core=None;raise ValueError('core differs from frozen infrastructure')
        return self._core

    @property
    def fresh(self):
        if self._fresh is None:
            path=self.root/self.profile['fresh_directory']/'fresh.duckdb'
            if file_hash(path)!=self.profile['semantics']['fresh_database_sha256']:raise ValueError('incremental sidecar changed')
            self._fresh=duckdb.connect(str(path),read_only=True)
        return self._fresh

    def __enter__(self):return self

    def __exit__(self,*args):
        if self._core is not None:self._core.connection.close()
        if self._fresh is not None:self._fresh.close()

    def universe_on(self,day,length=126,*,include_unknown=False):
        if not fresh_decision(day,self.profile['semantics']['fresh_start']):
            return self.core.universe_on(day,length,include_unknown=include_unknown)
        return self.fresh.execute("""SELECT w.security_id,p.symbol,p.membership_status,p.shape_research_status,p.source,p.basis
            FROM fresh_window_index w JOIN fresh_price p ON w.security_id=p.security_id AND w.decision_date=p.date
            WHERE w.decision_date=? AND w.length=? AND (w.supported_membership OR ?) ORDER BY w.security_id""",
            [pd.Timestamp(day).date(),length,include_unknown]).df()

    def window(self,security_id,decision_date,length=60,*,include_unknown=False,dataset=True):
        start=self.profile['semantics']['fresh_start']
        if not fresh_decision(decision_date,start):
            return self.core.window(security_id,decision_date,length,include_unknown=include_unknown,dataset=dataset)
        if length not in self.core.manifest['rules']['windows']:raise ValueError('unsupported window length')
        rows=self.fresh.execute("""SELECT * FROM fresh_window_index WHERE security_id=? AND decision_date=? AND length=?
                                 AND (supported_membership OR ?)""",[security_id,pd.Timestamp(decision_date).date(),length,include_unknown]).df()
        if rows.empty:raise ValueError('no safe Fresh decision window')
        m=rows.iloc[0].to_dict()
        f=self.fresh.execute('SELECT * FROM prices WHERE security_id=? AND date BETWEEN ? AND ? ORDER BY date',
                            [security_id,m['window_start'],m['decision_date']]).df()
        validate_input(f,decision_date)
        if len(f)!=length or not f.shape_research_ready.all():raise ValueError('incomplete/quarantined Fresh input')
        if not fresh_decision(f.date.max(),start):raise ValueError('Test cannot be backfilled as Fresh')
        normalized=normalize_window(f,decision_date)
        m.update({'window_end':m['decision_date'],'historical_ticker':f.symbol.iloc[-1],'split_assignment':'fresh_oos',
                  'source':f.source.iloc[0],'adjustment_mode':f.basis.iloc[0],
                  'source_hash':semantic_hash(f[['date','source_hash']].astype(str).values.tolist()),
                  'ohlcv_hash':canonical_hash(f),'normalized_hash':canonical_hash(normalized),'dataset_version':self.fingerprint,
                  'membership_status':f.membership_status.iloc[-1],
                  'shape_readiness_status':'READY_WITH_MINOR_UNCERTAINTY' if (f.shape_research_status!='READY').any() else 'READY',
                  'evaluation_status':'DATA_PREPARATION_ONLY; pre-F freeze not asserted',
                  'lookback_before_f_allowed':True,'labels_in_input':False})
        return ShapeWindow(m,f[['date','symbol','open','high','low','close','volume','basis','source']].copy(),normalized)

    def evaluation_window(self,security_id,decision_date,length,freeze_receipt,**kwargs):
        if not fresh_decision(decision_date,self.profile['semantics']['fresh_start']):raise ValueError('Fresh decision date required')
        validate_freeze(freeze_receipt,self.profile['semantics']['fresh_start'])
        w=self.window(security_id,decision_date,length,**kwargs)
        w.metadata['evaluation_status']='PRE_F_FREEZE_RECEIPT_VERIFIED; outcomes remain external'
        return w

    def feature_window(self,security_id,decision_date,length=126,**kwargs):
        w=self.window(security_id,decision_date,length,dataset=False,**kwargs)
        f=w.normalized.set_index('date');out=f.copy()
        out['return_1']=f.close.pct_change(fill_method=None)
        out['range_fraction']=(f.high-f.low)/f.close
        out['volume_relative_20']=f.volume/f.volume.rolling(20,min_periods=20).mean()
        return out

    def strategy2_feature_window(self,security_id,decision_date,spy_close,qqq_close,length=126,**kwargs):
        spy=reject_future_benchmark(spy_close,decision_date);qqq=reject_future_benchmark(qqq_close,decision_date)
        if not fresh_decision(decision_date,self.profile['semantics']['fresh_start']):
            return self.core.strategy2_feature_window(security_id,decision_date,spy,qqq,length,**kwargs)
        from radar.features.base import compute_base_features
        from radar.features.strategy2 import compute_strategy2_features
        w=self.window(security_id,decision_date,length,dataset=False,**kwargs);f=w.normalized.set_index('date')
        base=compute_base_features(f)
        absolute={'avg_volume_20','avg_dollar_volume_20'} | {x for x in base if x.startswith(('ma_','atr_','high_','low_')) and not x.startswith(('atr_pct_','atr_contraction'))}
        out=pd.concat([base.drop(columns=sorted(absolute)),compute_strategy2_features(f,spy,qqq)],axis=1)
        out['symbol']=w.ohlcv.symbol.values;out['security_id']=security_id
        return out.reset_index().set_index(['date','symbol'])


def shape_research_universe_v1(root):
    return ResearchInfrastructure(root)

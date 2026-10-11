"""Standalone offline provenance and causal-boundary audit for generated tasks."""
from collections import Counter
import json
from pathlib import Path
import numpy as np
import pandas as pd
from .history import CHANNELS
from .numeric import digest, LENGTHS
from .render import candle_svg
from .store import BoxStore, GateError


def verify_bundle(root):
    store=BoxStore(root,'smoke')
    dates=[];securities=[]
    for r in store.rows:
        t=pd.Timestamp(r['decision_date'])
        if r['split'] not in ('train','validation') or t>=pd.Timestamp('2025-09-09'):
            raise GateError('outside development decision domain')
        dates.append(t);securities.append(r['security_id'])
        anchor=None
        for scale in ('daily','weekly','monthly'):
            meta=r['scales'][scale]
            raw=(store.root/'raw'/meta['raw_file']).read_bytes()
            if digest(raw)!=meta['raw_hash']:raise GateError('raw drift')
            f=pd.DataFrame(json.loads(raw),columns=['date',*CHANNELS]);f.date=pd.to_datetime(f.date)
            if f.empty or f.date.iloc[-1]!=t or f.date.gt(t).any() or f.date.duplicated().any():
                raise GateError('post-T or incomplete scale')
            if len(f)!=meta['length'] or len(f)>LENGTHS[scale] or meta['available']!=(len(f)==LENGTHS[scale]):
                raise GateError('wrong scale/mask')
            if scale=='daily':anchor=float(f.close.iloc[-1])
            values=f[list(CHANNELS)].to_numpy(dtype=float)
            median=max(float(np.median(values[:,4])),1.)
            expected=np.column_stack([np.log(values[:,:4]/anchor),
                                      np.log1p(values[:,4])/np.log1p(median)]).astype('<f4')
            actual=np.load(store.root/'numeric'/meta['tensor_file'],allow_pickle=False)
            if not np.array_equal(actual,expected) or digest(actual.tobytes())!=meta['tensor_hash']:
                raise GateError('tensor inconsistent with displayed raw prefix')
            svg=(store.root/'charts'/meta['chart_file']).read_bytes()
            if svg!=candle_svg(f,scale.title()) or digest(svg)!=meta['chart_hash']:
                raise GateError('render inconsistent with numeric prefix')
            if any(term.encode() in svg for term in (r['security_id'],r['decision_date'],'candidate_score')):
                raise GateError('private information in chart')
    if len(set(securities))!=len(securities):raise GateError('overlapping security tasks')
    return {'tasks':len(store.rows),'unique_securities':len(set(securities)),
            'strata':dict(Counter(r['stratum'] for r in store.rows)),
            'splits':dict(Counter(r['split'] for r in store.rows)),
            'years':dict(Counter(str(t.year) for t in dates)),
            'manifest_hash':store.receipt['manifest_hash']}

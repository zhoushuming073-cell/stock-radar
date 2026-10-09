"""Quant-guided sampling, consuming frozen historical indices read-only.

The bulk reader is an adapter, not a new database or an eligibility policy.
Every selected numeric window is rechecked against the frozen public API.
"""
from __future__ import annotations

from dataclasses import replace
from hashlib import sha256
from importlib.metadata import version
import json
from pathlib import Path
import re

import numpy as np
import pandas as pd
import yaml

from radar.pit.features import file_hash
from radar.research.infrastructure import shape_research_universe_v1
from .labeling import VisionPilotConfig, _render_rows, _add_repeats, _build_pairs, _calendar_guard, _opaque_id
from .contracts import validate_sample_manifest, validate_pair_manifest
from .quant_features import array_features, features_at, stratum, DIMENSIONS
from .render import RENDERER_VERSION
from .verification import verify


def load_quant_config(path):
    cfg=yaml.safe_load(Path(path).read_text(encoding='utf-8'))
    if cfg['allowed_splits'] != ['train','validation'] or cfg['window_lengths'] != [60,126]:
        raise ValueError('only frozen Train/Validation and 60/126 windows')
    p=Path(cfg['output_dir'])
    if p.is_absolute() or '..' in p.parts or p.parts[:2] != ('data','vision-research') or 'pilot' in str(p):
        raise ValueError('new isolated private output directory required')
    if not cfg['version'] or not cfg['feature_version'] or cfg['scan']['session_stride'] < 1:
        raise ValueError('version and positive stride required')
    if sum(cfg['sampling']['quotas'].values()) != cfg['single_count'] or set(cfg['sampling']['quotas']) != {'high','medium','boundary','conflict','control'}:
        raise ValueError('five explicit quotas must total sample count')
    if cfg['single_count'] < 1 or not 0 <= cfg['repeat_fraction'] <= .5:
        raise ValueError('invalid sample counts')
    if cfg['sampling']['minimum_security_cooldown'] < 126:
        raise ValueError('overlap protection cannot be weakened')
    weights=cfg['scores']['weights']
    if set(weights)!=set(DIMENSIONS) or min(weights.values())<0 or abs(sum(weights.values())-1)>1e-9 or weights['entry_location']>=1:
        raise ValueError('invalid dimension weights')
    for k,v in cfg['scores'].items():
        if k.endswith('_weights'):
            if len(v)!=4 or min(v)<0 or abs(sum(v)-1)>1e-9: raise ValueError('invalid component weights')
        elif isinstance(v,list) and (len(v) not in (2,4) or any(a>=b for a,b in zip(v,v[1:]))):
            raise ValueError('strictly ordered fuzzy knots required: '+k)
    for k in ('concentration_penalty','pullback_depth_weight','breakdown_penalty'):
        if not 0<=cfg['scores'][k]<=1: raise ValueError('invalid penalty weight')
    return cfg


def issuer_key(sid):
    m=re.match(r'^SEC-(\d{10})-',sid)
    return ('CIK-'+m.group(1),True) if m else (sid,False)


def normalized_array(values, dates, basis, actions, decision):
    """Same arithmetic as frozen normalize_window; rechecked for ALL selected X."""
    a=np.stack(values).astype(float,copy=True)
    dates=np.asarray(dates,dtype='datetime64[ns]')
    if len(dates)!=len(a) or (dates>np.datetime64(decision)).any() or len(np.unique(dates))!=len(dates) or (np.diff(dates)<np.timedelta64(0,'ns')).any():
        raise ValueError('future/duplicate/unordered bulk window')
    if basis=='raw':
        for effective,factor in actions:
            if effective<=pd.Timestamp(decision):
                if not np.isfinite(factor) or factor<=0: raise ValueError('invalid split factor')
                before=dates<np.datetime64(effective)
                a[before,:4]/=factor
                a[before,4]*=factor
    elif basis!='split': raise ValueError('unknown basis')
    a[:,:4]/=a[0,3]
    a[:,4]/=max(a[:,4].max(),1e-100)
    return a


def scan(api,cfg,progress=None):
    c=api.core.connection
    days=c.execute("""select distinct decision_date from visual_window_index
        where supported_membership and split_assignment in ('train','validation') and length in (60,126)
        order by decision_date""").df().decision_date
    grid=list(days.iloc[::cfg['scan']['session_stride']])
    _calendar_guard(pd.Series(grid))
    actions={sid:[(pd.Timestamp(d),float(f)) for d,f in g[['date','factor']].itertuples(index=False,name=None)]
             for sid,g in c.execute('select security_id,date,factor from split_action order by date').df().groupby('security_id')}
    records=[]; audit=[]
    for day in grid:
        # Source selection matches window() priority; eligibility remains the frozen index.
        rows=c.execute("""with w as (
            select * from visual_window_index where decision_date=? and length in (60,126)
            and supported_membership and split_assignment in ('train','validation')
            qualify row_number() over(partition by security_id,decision_date,length order by priority)=1)
            select w.security_id,w.decision_date,w.length,w.split_assignment,w.membership_status,
            w.shape_research_status,w.series_id,w.basis,
            list(p.date order by p.date) as dates,
            list([p.open,p.high,p.low,p.close,p.volume] order by p.date) as bars,
            bool_and(p.shape_research_ready) as ready
            from w join shape_price p on p.series_id=w.series_id and p.date between w.window_start and w.decision_date
            group by all order by w.security_id,w.length""",[pd.Timestamp(day).date()]).df()
        excl=c.execute("""select membership_status,shape_research_status,supported_membership,count(*) n
            from visual_window_index where decision_date=? and length in (60,126)
            and split_assignment in ('train','validation') group by all""",[pd.Timestamp(day).date()]).df()
        population=c.execute("""select membership_status,count(distinct security_id) n from population
            where date=? and eligible group by 1""",[pd.Timestamp(day).date()]).df()
        audit.append({'date':str(pd.Timestamp(day).date()),'eligible_membership_counts':population.to_dict('records'),
                      'index_status_counts':excl.to_dict('records'),'scored_windows':len(rows),
                      'eligible_security_days':int(rows.security_id.nunique())})
        for r in rows.itertuples(index=False):
            if not r.ready or len(r.bars)!=r.length or r.membership_status not in ('confirmed_member','probable_member'):
                raise ValueError('bulk adapter crossed frozen safety gate')
            a=normalized_array(r.bars,r.dates,r.basis,actions.get(r.security_id,()),r.decision_date)
            f=array_features(a,cfg)
            ik,known=issuer_key(r.security_id)
            records.append(dict(security_id=r.security_id,decision_date=r.decision_date,length=r.length,
                  split_assignment=r.split_assignment,membership_status=r.membership_status,
                  shape_research_status=r.shape_research_status,issuer_key=ik,issuer_known=known,
                  candidate_stratum=stratum(f,cfg),year=pd.Timestamp(r.decision_date).year,
                  feature_version=cfg['feature_version'],**f))
        if progress: progress(f'scanned {len(audit)}/{len(grid)} sessions; {len(records)} windows')
    return pd.DataFrame(records),audit


def select(pool,cfg):
    """Two-stage uniform hash sampling; record CONDITIONAL stage probabilities.

    One representative per issuer first; balance year/window cells second.
    These are NOT unconditional market inclusion weights (strata are random).
    """
    pool=pool.copy()
    pool['draw']=pool.apply(lambda r:_opaque_id(cfg['seed'],'representative',r.security_id,r.decision_date,r.length,size=64),axis=1)
    pool['issuer_window_count']=pool.groupby('issuer_key').issuer_key.transform('size')
    reps=pool.sort_values('draw').drop_duplicates('issuer_key').copy()
    reps['stage1_probability']=1/reps.issuer_window_count
    # Independent hash domain: minimum stage-1 hashes are NOT uniform across
    # issuers with different window counts and cannot be reused for stage 2.
    reps['selection_draw']=reps.apply(lambda r:_opaque_id(cfg['seed'],'stage2',r.issuer_key,r.decision_date,r.length,size=64),axis=1)
    quotas=dict(cfg['sampling']['quotas']); chosen=[]; used=set()
    anchors={x['security_id']:x['kind'] for x in cfg['anchors']}
    for sid,kind in anchors.items():
        subset=reps[reps.security_id==sid]
        if subset.empty: raise ValueError('required verified historical anchor missing: '+sid)
        row=subset.iloc[0].to_dict(); layer=row['candidate_stratum']
        row.update(sampling_layer=layer,stage2_probability=1.,sampling_cell='forced-historical-anchor',anchor_kind=kind)
        chosen.append(row); used.add(row['issuer_key']); quotas[layer]-=1
    def take(layer,frame,n):
        if n<0: raise ValueError('anchor count exceeds quota')
        groups={key:g.sort_values('selection_draw') for key,g in frame.groupby(['year','length'],sort=True)}
        allocations={key:0 for key in groups}
        while sum(allocations.values())<n:
            before=sum(allocations.values())
            for key,g in groups.items():
                if allocations[key]<len(g) and sum(allocations.values())<n: allocations[key]+=1
            if before==sum(allocations.values()): raise ValueError('insufficient safe stratum: '+layer)
        for key,g in groups.items():
            for row in g.head(allocations[key]).to_dict('records'):
                row.update(sampling_layer=layer,stage2_probability=allocations[key]/len(g),
                           sampling_cell=f'{layer}/{key[0]}/{key[1]}',anchor_kind=None)
                chosen.append(row); used.add(row['issuer_key'])
    # Controls sampled before Quant strata; no score condition on ordinary controls.
    take('control',reps[~reps.issuer_key.isin(used)],quotas['control'])
    for layer in ('high','medium','boundary','conflict'):
        take(layer,reps[(reps.candidate_stratum==layer)&~reps.issuer_key.isin(used)],quotas[layer])
    out=pd.DataFrame(chosen)
    if len(out)!=cfg['single_count'] or out.issuer_key.duplicated().any() or out.security_id.duplicated().any():
        raise ValueError('sample size or overlap/issuer violation')
    out['conditional_path_probability']=out.stage1_probability*out.stage2_probability
    return out,reps


def stats(frame):
    cols=[c for c in frame.select_dtypes(include='number') if c not in
          {'length','year','window_length','issuer_window_count','stage1_probability','stage2_probability','conditional_path_probability'}]
    return {'count':len(frame),'by_year':frame.year.value_counts().sort_index().to_dict(),
            'by_window':frame.length.value_counts().sort_index().to_dict(),
            'by_split':frame.split_assignment.value_counts().to_dict(),
            'by_stratum':frame.candidate_stratum.value_counts().to_dict(),
            'distributions':frame[cols].describe(percentiles=[.05,.25,.5,.75,.95]).to_dict()}


def build(root,config_path,progress=print,scan_cache=None):
    root=Path(root).resolve(); cfg=load_quant_config(config_path); output=root/cfg['output_dir']
    if output.exists(): raise ValueError('immutable bundle already exists; use a NEW configured output for replay')
    output.mkdir(parents=True)
    code_hash=sha256(b''.join(Path(p).read_bytes() for p in [__file__,Path(__file__).with_name('quant_features.py')])).hexdigest()
    with shape_research_universe_v1(root) as api:
        if scan_cache is None:
            pool,audit=scan(api,cfg,progress)
        else:
            cache=Path(scan_cache)
            proof=json.loads((cache/'scan-cache-verification.json').read_text(encoding='utf-8'))
            receipt=json.loads((cache/'bundle-receipt.json').read_text(encoding='utf-8'))
            old=load_quant_config(cache/'config.yaml')
            if proof['status']!='PASS' or proof['feature_kernel_sha256']!=file_hash(Path(__file__).with_name('quant_features.py')) or receipt['infrastructure_hash']!=api.fingerprint:
                raise ValueError('scan cache provenance mismatch')
            for key in ('scores','scan','allowed_splits','window_lengths','feature_version'):
                if old[key]!=cfg[key]: raise ValueError('scan cache configuration mismatch')
            for name in ('scanned-features.parquet','sampling-audit.json','config.yaml'):
                if file_hash(cache/name)!=receipt['artifact_hashes'][name]: raise ValueError('scan cache hash mismatch')
            pool=pd.read_parquet(cache/'scanned-features.parquet')
            audit=json.loads((cache/'sampling-audit.json').read_text(encoding='utf-8'))['per_session']
            if progress: progress(f'reusing verified causal scan: {len(pool)} windows; rescoring selected windows against frozen API')
        chosen,reps=select(pool,cfg)
        for r in chosen.itertuples():
            w=api.window(r.security_id,r.decision_date,r.length)
            actual=features_at(w.normalized,r.decision_date,cfg)
            if any(not np.isclose(actual[k],getattr(r,k),rtol=1e-10,atol=1e-8) for k in actual):
                raise ValueError('bulk/public frozen window feature mismatch')
        prefix='/data/local-files/?d='+Path(cfg['output_dir']).relative_to('data').as_posix()
        pilot=VisionPilotConfig(cfg['version']+'-'+file_hash(config_path)[:12]+'-'+code_hash[:12],cfg['seed'],cfg['single_count'],0,
                 cfg['repeat_fraction'],(60,126),('train','validation'),cfg['output_dir'],'data',prefix,tuple(cfg['anchors']))
        anchor_map={(r.security_id,str(pd.Timestamp(r.decision_date).date()),r.length):r.anchor_kind
                    for r in chosen.itertuples() if r.anchor_kind is not None}
        manifest=validate_sample_manifest(_add_repeats(_render_rows(root,api,chosen,pilot,anchor_map),pilot))
        pairs=validate_pair_manifest(_build_pairs(manifest,pilot))
        unchanged=file_hash(api.core.directory/'shape.duckdb')==api.core.manifest['database_sha256']
        if not unchanged: raise ValueError('frozen database changed')
        infra=api.fingerprint
    manifest.to_parquet(output/'sample-manifest.parquet',index=False)
    pairs.to_parquet(output/'pair-manifest.parquet',index=False)
    chosen=chosen.merge(manifest[manifest.task_kind=='single'][['task_id','security_id','decision_date','window_length','normalized_hash','ohlcv_hash','image_sha256']],
                        left_on=['security_id','decision_date','length'],right_on=['security_id','decision_date','window_length'],validate='one_to_one')
    chosen.to_parquet(output/'quant-features.parquet',index=False)
    pool.to_parquet(output/'scanned-features.parquet',index=False)
    reps.to_parquet(output/'sampling-frame.parquet',index=False)
    singles=[{'data':{'image':prefix+'/'+r.image_path,'task_id':r.task_id}}
             for r in manifest.assign(order=manifest.task_id.map(lambda x:_opaque_id(cfg['seed'],'display',x))).sort_values('order').itertuples()]
    for name,value in [('label-studio-single-tasks.json',singles),('label-studio-pair-tasks.json',[])]:
        (output/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    selected_stats=stats(chosen); selected_stats['sampling_layers']=chosen.sampling_layer.value_counts().to_dict()
    selected_stats['unknown_issuer_samples']=int((~chosen.issuer_known).sum())
    audit_summary={'scanned_sessions':len(audit),'eligible_security_days_scored':sum(x['eligible_security_days'] for x in audit),
         'scanned':stats(pool),'selected':selected_stats,'per_session':audit,
         'sampling_probability_semantics':'stage1: uniform within issuer; stage2: conditional on realized representative frame/year/window cell. Product is a conditional path probability, NOT a marginal full-market IPW weight.',
         'selection_bias':'Quant-guided candidate distribution; finite temporal grid; observed historical universe with missingness, not complete US market.',
         'issuer_policy':'one known CIK or root security per batch; non-CIK issuer equivalence unverified, no ticker/name merging',
         'ordinary_control_policy':'uniform representative-frame control draw without score condition; anchors are forced historical retention checks',
         'anchors':[{'kind':r.anchor_kind,'layer':r.sampling_layer} for r in chosen.itertuples() if r.anchor_kind is not None]}
    (output/'sampling-audit.json').write_text(json.dumps(audit_summary,ensure_ascii=False,indent=2,default=str),encoding='utf-8')
    (output/'config.yaml').write_bytes(Path(config_path).read_bytes())
    names=['sample-manifest.parquet','pair-manifest.parquet','label-studio-single-tasks.json','label-studio-pair-tasks.json',
           'quant-features.parquet','scanned-features.parquet','sampling-frame.parquet','sampling-audit.json','config.yaml']
    receipt={'version':cfg['version'],'feature_version':cfg['feature_version'],'infrastructure_hash':infra,
      'renderer_version':RENDERER_VERSION,'single_unique':cfg['single_count'],'single_repeats':len(manifest)-cfg['single_count'],
      'unique_securities':cfg['single_count'],'pairs':0,'future_outcomes_read':False,'strategy2_scores_read':False,
      'unknown_membership_included':False,'source_read_only_and_unchanged':unchanged,'local_files_prefix':prefix,
      'label_schema_version':'quant-human-v1','config_sha256':file_hash(config_path),'implementation_sha256':code_hash,
      'scan_cache_reused':str(Path(scan_cache).relative_to(root)) if scan_cache else None,
      'renderer_dependencies':{n:version(n) for n in ['mplfinance','matplotlib','numpy','pandas','Pillow']},
      'artifact_hashes':{n:file_hash(output/n) for n in names}}
    (output/'bundle-receipt.json').write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    result=verify_quant(output)
    (output/'verification.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def verify_quant(bundle):
    bundle=Path(bundle); base=verify(bundle)
    receipt=json.loads((bundle/'bundle-receipt.json').read_text())
    cfg=load_quant_config(bundle/'config.yaml')
    for n,h in receipt['artifact_hashes'].items():
        if file_hash(bundle/n)!=h: raise ValueError('quant artifact hash mismatch: '+n)
    if receipt['label_schema_version']!='quant-human-v1' or receipt['feature_version']!=cfg['feature_version']:
        raise ValueError('quant label/feature version mismatch')
    manifest=pd.read_parquet(bundle/'sample-manifest.parquet'); q=pd.read_parquet(bundle/'quant-features.parquet')
    orig=manifest[manifest.task_kind=='single'].set_index('task_id')
    if set(q.task_id)!=set(orig.index) or q.task_id.duplicated().any(): raise ValueError('Q/X cardinality mismatch')
    for r in q.itertuples():
        m=orig.loc[r.task_id]
        for k in ['security_id','decision_date','normalized_hash','ohlcv_hash','image_sha256','split_assignment']:
            if getattr(r,k)!=m[k]: raise ValueError('Q/X mapping mismatch')
        norm=pd.read_parquet(bundle/f'windows/{m.blind_id}-normalized.parquet')
        f=features_at(norm,m.decision_date,cfg)
        if any(not np.isclose(getattr(r,k),v,rtol=1e-10,atol=1e-8) for k,v in f.items()): raise ValueError('Q recomputation mismatch')
        if not 0<r.conditional_path_probability<=1: raise ValueError('invalid conditional sampling probability')
    if q.issuer_key.duplicated().any() or q.security_id.duplicated().any(): raise ValueError('overlapping issuer/security samples')
    base.update(quant_rows=len(q),quant_recomputed=len(q),future_outcomes_read=False,label_schema_version='quant-human-v1')
    return base

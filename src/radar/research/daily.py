"""Read-only latest-session product; current assets never stand in for historical PIT."""
from collections import Counter
import csv
from io import StringIO
import json
from uuid import uuid4
from pathlib import Path
import duckdb
import pandas as pd
from radar.models import AssetRecord
from radar.universe.filters import filter_eligible_assets
from radar.pit.shape import canonical_hash
from radar.research.candidates import configurations,q1,q2,rank_candidates,fingerprint,code_hash
from radar.research.sessions import completed_session,require_session,calendar

COLUMNS=['date','open','high','low','close','volume']

def current_inputs(database,asof=None,now=None):
    target=completed_session(now)
    if asof is not None:require_session(asof,now=now)
    with duckdb.connect(str(database),read_only=True) as c:
        latest=c.execute("select max(date) from daily_bars where date<=?",[target]).fetchone()[0]
        if latest is None:raise ValueError('no completed local bars')
        actual=asof or str(latest)
        require_session(actual,now=now)
        if actual>str(latest):raise ValueError('requested completed session has no local bars; update data')
        assets=c.execute('select * from assets where last_seen=(select max(last_seen) from assets)').df()
        eligible=filter_eligible_assets([AssetRecord(**r) for r in assets.to_dict('records')])
        names={a.symbol:a.name for a in eligible}
        if not eligible:return actual,target,names,pd.DataFrame(columns=['symbol',*COLUMNS,'provider','feed','adjustment'])
        c.register('eligible_symbols',pd.DataFrame({'symbol':list(names)}))
        frame=c.execute("""select b.symbol,b.date,b.open,b.high,b.low,b.close,b.volume,b.provider,b.feed,b.adjustment
          from daily_bars b join eligible_symbols e using(symbol) where date<=?
          qualify row_number() over(partition by b.symbol order by date desc)<=430
          order by symbol,date""",[actual]).df()
    return actual,target,names,frame

def validate_current(frame,asof):
    if frame.empty or str(pd.Timestamp(frame.date.iloc[-1]).date())!=asof:raise ValueError('missing_decision_bar')
    if frame[['provider','feed','adjustment']].drop_duplicates().shape[0]!=1:raise ValueError('mixed_source_or_basis')
    if frame.adjustment.iloc[0]!='split':raise ValueError('current_requires_homogeneous_split_bars')
    if frame.date.duplicated().any() or not frame.date.is_monotonic_increasing:raise ValueError('duplicate_or_unordered')
    sessions=calendar().sessions_in_range(frame.date.iloc[0],asof)
    if list(pd.to_datetime(frame.date))!=list(sessions):raise ValueError('missing_or_nonexchange_sessions')
    return frame[COLUMNS].copy()

def snapshot(root,asof=None,method='all',top=20,now=None,progress=None):
    root=Path(root)
    if method not in {'all','q1','q2'} or not isinstance(top,int) or isinstance(top,bool) or not 1<=top<=100:
        raise ValueError('method q1|q2|all and top 1..100 required')
    day,target,names,frame=current_inputs(root/'data/market.duckdb',asof,now)
    a,b=configurations(root);ch=code_hash();qh=fingerprint(a['scores']);bh=fingerprint(b.__dict__)
    skips=Counter();rows={'q1':[],'q2':[]};scored={'q1':0,'q2':0};dists={'q1':[],'q2':[]};rejected={'q1':Counter(),'q2':Counter()}
    datahash=fingerprint({'assets':names,'bars':pd.util.hash_pandas_object(frame,index=False).astype(str).tolist()})
    groups={s:g for s,g in frame.groupby('symbol',sort=True)}
    for i,s in enumerate(sorted(names)):
        try:
            f=validate_current(groups.get(s,pd.DataFrame()),day)
            source={'domain':'current_assets_latest_only','data_hash':datahash,
                    'window_hash':canonical_hash(f),'config_hash':None,'code_hash':ch}
        except ValueError as e:skips[str(e)]+=1;continue
        for key,fn,cfg,cfg_hash in [('q1',q1,a,qh),('q2',q2,b,bh)]:
            if method not in {'all',key}:continue
            try:r=fn(f,day,cfg,security_id='CURRENT:'+s,symbol=s,name=names[s],
                       provenance={**source,'config_hash':cfg_hash},
                       quality_flags=['CURRENT_SNAPSHOT_NOT_HISTORICAL_MEMBERSHIP','ASSET_CLASS_NOT_COMMON_ONLY','UNCERTIFIED_CORPORATE_ACTIONS'])
            except ValueError as e:rejected[key][str(e)]+=1;continue
            scored[key]+=1;dists[key].append(r.score)
            if r.status!='rejected':rows[key].append(r)
            else:rejected[key][r.reason_codes[0]]+=1
        if progress and i%250==0:progress(f'{i+1}/{len(names)} current eligible assets')
    result={'schema_version':'daily-quant-watchlist-v1','as_of':day,'latest_completed_session':target,
            'requested_as_of':asof,'stale':day<target,'freshness':'STALE' if day<target else 'CURRENT',
            'source':'current_snapshot/latest_only','universe_count':len(names),'scored_counts':scored,
            'data_hash':datahash,'code_hash':ch,'config_hashes':{'q1':qh,'q2':bh},'top':top,
            'excluded':dict(skips),'method_exclusions':{k:dict(v) for k,v in rejected.items()},
            'warning':'Research watchlist; no broker orders. Current assets include equity-like classes; not historical PIT. Scores across methods are not comparable.',
            'score_distributions':{k:pd.Series(v,dtype=float).describe(percentiles=[.1,.25,.5,.75,.9]).where(lambda x:x.notna(),None).to_dict() if v else {} for k,v in dists.items()}}
    for key in rows:
        ranked=rank_candidates(rows[key])
        result[key+'_counts']=dict(Counter(r.status for r in ranked))
        result[key]=[r.model_dump(mode='json') for r in ranked[:top]]
        result[key+'_all']=[r.model_dump(mode='json') for r in ranked]
    q1ids={r.security_id for r in rows['q1']};q2ids={r.security_id for r in rows['q2']}
    result['overlap_count']=len(q1ids&q2ids)
    result['overlap']=[{'security_id':sid,'symbol':sid.removeprefix('CURRENT:'),
                       'methods':['q1_fuzzy_shape','q2_parallel_channel']} for sid in sorted(q1ids&q2ids)[:top]]
    return result

def save_snapshot(root,result):
    private=Path(root)/'data/research/daily-quant';private.mkdir(parents=True,exist_ok=True)
    encoded=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    digest=fingerprint(result);path=private/(result['as_of']+'-'+digest+'.json')
    try:
        with path.open('xb') as stream:stream.write(encoded)
    except FileExistsError:
        if path.read_bytes()!=encoded:raise ValueError('immutable snapshot differs')
    latest=private/'latest.json';tmp=private/('latest-'+uuid4().hex+'.tmp')
    try:
        tmp.write_bytes(encoded);tmp.replace(latest)
    finally:
        tmp.unlink(missing_ok=True)
    return path

def load_latest(root,method='all',top=20,now=None):
    if method not in {'all','q1','q2'} or not 1<=top<=100:raise ValueError('invalid method/top')
    path=Path(root)/'data/research/daily-quant/latest.json'
    if not path.exists():return {'state':'NOT_GENERATED','latest_completed_session':completed_session(now),'instruction':'Run the local Daily Scanner command'}
    r=json.loads(path.read_text());r['latest_completed_session']=completed_session(now);r['stale']=r['as_of']<r['latest_completed_session'];r['freshness']='STALE' if r['stale'] else 'CURRENT'
    r['snapshot_hash']=fingerprint(json.loads(path.read_text()))
    for k in ['q1','q2']:r[k]=r[k+'_all'][:top] if method in {'all',k} else [];r.pop(k+'_all',None)
    r['overlap']=r['overlap'][:top] if method=='all' else []
    return r

def csv_rows(result):
    s=StringIO();w=csv.DictWriter(s,fieldnames=['method','version','decision_date','symbol','name','rank','score','status','reason_codes'])
    w.writeheader()
    for k in ['q1','q2']:
        for row in result[k]:w.writerow({f:json.dumps(row[f]) if isinstance(row[f],list) else row[f] for f in w.fieldnames})
    return s.getvalue()


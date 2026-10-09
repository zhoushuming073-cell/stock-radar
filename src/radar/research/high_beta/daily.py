"""Q2 v1.2 current-market adapter, isolated from the frozen v1.1 Daily product."""
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict
from pathlib import Path
import hashlib
import json
import re
from uuid import uuid4

import duckdb
import pandas as pd

from radar.research.candidates import fingerprint
from radar.research.daily import current_inputs
from radar.research.high_beta.channel import VERSION,MarketEvidence,analyze,candidate,rank,settings
from radar.research.sessions import completed_session


def source_hash():
    folder=Path(__file__).parent
    files=[folder/'channel.py',folder/'daily.py',folder.parent/'parallel_channel.py',
           folder.parent/'daily.py',folder.parent/'sessions.py',folder.parent.parent/'features/elasticity.py']
    return fingerprint({str(p.relative_to(folder.parent.parent)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})


def _issuer(name):
    # Match a known current instrument description, never merge historical IDs.
    text=re.sub(r'\b(?:class\s+[a-z0-9-]+\s+)?(?:common\s+(?:stock|shares)|ordinary\s+shares).*$', '',str(name),flags=re.I)
    return re.sub('[^a-z0-9]','',text.lower())


def listing_context(root,names,asof):
    """Current classification only. Unknown/conflicting classes stay quarantined.

    The local dated instrument directory can support a current common-stock
    description, not turn an observed issuer episode into verified historical
    membership. Stable current names are checked against its latest interval.
    """
    path=Path(root)/'data/security-master.csv'
    if not path.exists():return {s:False for s in names},{'classification_directory':'MISSING'}
    f=pd.read_csv(path,keep_default_na=False)
    f=f.loc[f.valid_from.le(asof) & f.valid_to.ge(str((pd.Timestamp(asof)-pd.Timedelta(days=7)).date()))]
    groups={s:g for s,g in f.groupby('symbol',sort=True)};result={}
    for symbol,name in names.items():
        g=groups.get(symbol)
        if g is None:result[symbol]=False;continue
        g=g.loc[g.security_type.eq('common') & g.security_name.map(_issuer).eq(_issuer(name))]
        # Even same issuer may have several security classes: never choose one.
        result[symbol]=bool(name and len(g)==1 and g.iloc[0].eligible in [True,'True','true'])
    return result,{'classification_directory_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
                  'scope':'Current listing classification; stale directory up to7 calendar days, exact normalized issuer description, unique common class. NOT historical identity certification.'}


def score(payload):
    symbol,name,frame,spy,qqq,asof,common,cfg,provenance=payload
    proof=MarketEvidence(scope='current_listing',identity_trusted=bool(name) and common,
        common_stock=common,source='alpaca',feed='sip',adjustment='split',joint_price_volume_adjustment=True)
    result=analyze(frame,asof,spy,qqq,proof,cfg)
    c=candidate(result,security_id='CURRENT:'+symbol,symbol=symbol,name=name,provenance=provenance)
    return c


def snapshot(root,asof=None,workers=1,progress=None):
    root=Path(root)
    if workers not in (1,2,4):raise ValueError('workers must be1,2,4')
    day,target,names,frame=current_inputs(root/'data/market.duckdb',asof)
    cfg=settings(root);ch=source_hash();classifications,class_proof=listing_context(root,names,day)
    with duckdb.connect(str(root/'data/market.duckdb'),read_only=True) as c:
        refs=c.execute("select symbol,date,close,provider,feed,adjustment from daily_bars where symbol in ('SPY','QQQ') and date<=? order by symbol,date",[day]).df()
    spy=refs.loc[refs.symbol.eq('SPY')];qqq=refs.loc[refs.symbol.eq('QQQ')]
    data_hash=fingerprint({'names':names,'bars':pd.util.hash_pandas_object(frame,index=False).astype(str).tolist(),
        'benchmark':pd.util.hash_pandas_object(refs,index=False).astype(str).tolist(),'classification':class_proof})
    groups={s:g for s,g in frame.groupby('symbol',sort=True)}
    provenance={'domain':'current_listing_latest_only','data_hash':data_hash,'config_hash':fingerprint(asdict(cfg)),
        'code_hash':ch,'absolute_amount_basis':'Alpaca SIP joint split-adjusted price and volume',**class_proof}
    tasks=[(s,names[s],groups.get(s,pd.DataFrame(columns=frame.columns)),spy,qqq,day,classifications[s],cfg,provenance) for s in sorted(names)]
    records=[]
    def collect(iterator):
        for i,r in enumerate(iterator):
            records.append(r)
            if progress and i%500==0:progress(f'{i+1}/{len(tasks)} current assets; Q2 v1.2')
    if workers==1:collect(map(score,tasks))
    else:
        with ThreadPoolExecutor(max_workers=workers) as pool:collect(pool.map(score,tasks))
    admitted=[r for r in records if r.window_metadata['analysis']['market_qualified']]
    structures=[r for r in admitted if r.window_metadata['analysis']['structure_qualified']]
    ranked=rank(records)
    beta_pass=0;liquid_pass=0;both_pass=0;valid=0
    for r in records:
        f=r.window_metadata['analysis']['market']
        if f is None:continue
        valid+=1;b=f['beta']['spy_126']
        beta_ok=b['value'] is not None and not b['outliers'] and b['value']>=cfg.beta_minimum
        liquid=f['adv20_dollar']>=cfg.adv20_minimum
        beta_pass+=int(beta_ok);liquid_pass+=int(liquid);both_pass+=int(beta_ok and liquid)
    funnel={'total_current_eligible_assets':len(names),'common_listing_supported':sum(classifications.values()),
        'valid_market_data':valid,'beta_qualified':beta_pass,'liquidity_qualified':liquid_pass,'both_market_gates':both_pass,
        'channel_qualified':len(structures),'near_support':sum(r.window_metadata['analysis']['near_support'] for r in structures),
        'early_reversal':sum(r.status=='qualified' for r in ranked),'watch_or_pending':sum(r.status!='qualified' for r in ranked)}
    result={'schema_version':'q2-high-beta-daily-v1','version':VERSION,'as_of':day,'latest_completed_session':target,
        'freshness':'STALE' if day<target else 'CURRENT','config':asdict(cfg),'config_hash':fingerprint(asdict(cfg)),
        'code_hash':ch,'data_hash':data_hash,'provenance':provenance,'funnel':funnel,
        'reason_counts':dict(Counter(reason for r in records for reason in r.reason_codes)),
        'candidates':[r.model_dump(mode='json') for r in ranked],
        'diagnostics':[r.model_dump(mode='json') for r in records],
        'industry_distribution':{'Unknown':len(ranked)},'industry_classification':'No trusted sector dataset installed; no name-based sector inference.',
        'warning':'Research watchlist only. Entry readiness is an intention, not an order. Current instrument classification does not certify historical issuer continuity or absolute execution. No future outcomes used.'}
    return result


def save(root,result):
    directory=Path(root)/'data/research/high-beta-channel-v1.2/daily';directory.mkdir(parents=True,exist_ok=True)
    encoded=json.dumps(result,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
    path=directory/(result['as_of']+'-'+fingerprint(result)+'.json')
    try:
        with path.open('xb') as f:f.write(encoded)
    except FileExistsError:
        if path.read_bytes()!=encoded:raise ValueError('immutable Q2 v1.2 snapshot differs')
    temp=directory/('latest-'+uuid4().hex+'.tmp')
    try:temp.write_bytes(encoded);temp.replace(directory/'latest.json')
    finally:temp.unlink(missing_ok=True)
    return path


def latest(root,top=20):
    if not isinstance(top,int) or isinstance(top,bool) or not 1<=top<=100:raise ValueError('top must be1..100')
    path=Path(root)/'data/research/high-beta-channel-v1.2/daily/latest.json'
    if not path.exists():return {'state':'NOT_GENERATED','version':VERSION}
    original=json.loads(path.read_text());r={k:v for k,v in original.items() if k!='diagnostics'}
    r['snapshot_hash']=fingerprint(original);r['candidates']=r['candidates'][:top]
    r['latest_completed_session']=completed_session();r['freshness']='STALE' if r['as_of']<r['latest_completed_session'] else 'CURRENT'
    return r

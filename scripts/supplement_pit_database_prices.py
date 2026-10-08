"""Fill one evidenced missing security series; never splice or edit source DBs.

Uses the existing user Alpaca account and a historical symbol-asof boundary.
Raw responses are private/local, receipt metadata contains no credentials.
"""
import argparse
from datetime import datetime, time, timedelta, timezone
import json
from pathlib import Path
import shutil
from zoneinfo import ZoneInfo

import duckdb
import pandas as pd
import requests
import yaml

from radar.daily_update import credentials
from radar.features.elasticity import ElasticityConfig
from radar.features.scoring import load_research_config
from radar.pit.builder import digest
from radar.pit.database import HistoricalDatabase, validate_prices
from radar.pit.features import causal_identity_features, file_hash
from radar.research.pipeline import FEATURE_VERSION
from radar.schema import RESEARCH_COLUMNS


def capture(root, symbol, start, end, asof, *, benchmarks=False):
    rawdir=root/'data/pit/raw/database-construction'
    rawdir.mkdir(parents=True,exist_ok=True)
    symbols='SPY,QQQ' if benchmarks else symbol
    params={'timeframe':'1Day','start':datetime.combine(start,time.min,ZoneInfo('America/New_York')).isoformat(),
            'end':datetime.combine(end,time.max,ZoneInfo('America/New_York')).isoformat(),
            'adjustment':'raw','feed':'sip','asof':str(asof),'limit':10000,'sort':'asc'}
    params['symbols']=symbols
    url='https://data.alpaca.markets/v2/stocks/bars'
    cache=rawdir/(digest({'url':url,'request':params})+'.receipt.json')
    if cache.exists():
        receipt=json.loads(cache.read_text(encoding='utf-8'))
        path=rawdir/(receipt['raw_sha256']+'.raw')
        if file_hash(path)!=receipt['raw_sha256']:
            raise ValueError('supplement raw cache changed')
        return json.loads(path.read_text(encoding='utf-8')),receipt
    key,secret=credentials(root)
    response=requests.get(url,params=params,
        headers={'APCA-API-KEY-ID':key,'APCA-API-SECRET-KEY':secret},timeout=(10,45))
    # No headers, credential values, or request exception dumps are persisted.
    raw=response.content
    raw_hash=__import__('hashlib').sha256(raw).hexdigest()
    path=rawdir/(raw_hash+'.raw');path.write_bytes(raw)
    receipt={'url':url,'request':{**params,'symbols':symbols},'status':response.status_code,
             'raw_sha256':raw_hash,'retrieved_at':datetime.now(timezone.utc).isoformat(),
             'source_version':'Alpaca-v2:'+raw_hash,'license':'existing account local research; no raw redistribution'}
    cache.write_text(json.dumps(receipt,indent=2),encoding='utf-8')
    if response.status_code!=200:
        raise ValueError('historical source HTTP '+str(response.status_code))
    return response.json(),receipt


def normalize(payload, symbol, receipt, sid):
    if payload.get('next_page_token'):
        raise ValueError('incomplete source pagination; do not install')
    bars=payload.get('bars',{}).get(symbol,[])
    if not bars:
        raise ValueError('source returned no evidenced bars')
    rows=[]
    for b in bars:
        rows.append(dict(security_id=sid,symbol=symbol,date=pd.Timestamp(b['t']).tz_convert('America/New_York').date(),
            open=b['o'],high=b['h'],low=b['l'],close=b['c'],volume=b['v'],source='Alpaca SIP',
            source_version=receipt['source_version'],retrieved_at=pd.Timestamp(receipt['retrieved_at']),basis='raw',
            action_relation='raw unchanged; material/terminal economics separate',conflict_state='no alternate price source available',
            source_database_sha256=receipt['raw_sha256']))
    frame=pd.DataFrame(rows)
    validate_prices(frame)
    return frame.sort_values('date')


def validate_scope(db, frame, asof):
    sid=frame.security_id.unique()
    if len(sid)!=1:
        raise ValueError('supplement requires one independently verified security')
    sid=sid[0]
    valid=db.connection.execute("SELECT symbol,valid_from,valid_to FROM ticker_episode WHERE security_id=? AND resolution_status='verified' AND eligible",[sid]).fetchall()
    if not valid or not any(start<=asof<=end for _,start,end in valid):
        raise ValueError('historical symbol asof outside verified identity')
    if db.connection.execute('SELECT count(*) FROM accepted_price WHERE security_id=?',[sid]).fetchone()[0]:
        raise ValueError('existing accepted series; replacement required, no splice')
    if db.connection.execute('SELECT count(*) FROM observed_price WHERE security_id=?',[sid]).fetchone()[0]:
        raise ValueError('existing legacy basis; no mixed source splice')
    for row in frame.itertuples():
        if not any(row.symbol==symbol and start<=row.date<=end for symbol,start,end in valid):
            raise ValueError('supplement price outside verified ticker interval')
    db.filter_frame(frame)


def supplement(root, sid, symbol, start, end, asof):
    pointer=root/'data/pit/construction/current.json'
    parent_dir=Path(json.loads(pointer.read_text(encoding='utf-8'))['directory'])
    # Verify identity/membership and actual need before any price request.
    with HistoricalDatabase(parent_dir) as db:
        probe=pd.DataFrame([dict(security_id=sid,symbol=symbol,date=start),dict(security_id=sid,symbol=symbol,date=end)])
        validate_scope(db,probe,asof)
        parent=db.manifest
        days=db.connection.execute('SELECT date FROM sessions WHERE date BETWEEN ? AND ? ORDER BY date',[start,end]).df()
    payload,receipt=capture(root,symbol,start,end,asof)
    frame=normalize(payload,symbol,receipt,sid)
    with HistoricalDatabase(parent_dir) as db:
        validate_scope(db,frame,asof)
    benchmark,bench_receipt=capture(root,symbol,start,end,asof,benchmarks=True)
    if benchmark.get('next_page_token'):
        raise ValueError('incomplete benchmark source pagination')
    benchmark_series={}
    for name in ('SPY','QQQ'):
        b=normalize(benchmark,name,bench_receipt,'BENCHMARK-'+name)
        benchmark_series[name]=b.set_index(pd.to_datetime(b.date)).close
    calendar=pd.DatetimeIndex(pd.to_datetime(days.date))
    indexed=frame.set_index(pd.to_datetime(frame.date))
    bars=indexed[['open','high','low','close','volume']].reindex(calendar)
    cfg_path=root/'config/research.yaml'
    if not cfg_path.exists():
        cfg_path=root/'config/phase2.yaml'
    cfg=load_research_config(cfg_path)
    raw_cfg=yaml.safe_load(cfg_path.read_text(encoding='utf-8'))['elasticity']
    ecfg=ElasticityConfig(**{key:raw_cfg[key] for key in ('history_window','history_min','burst_quantile','hit_5_weight','hit_10_weight')})
    feature=causal_identity_features(bars,benchmark_series['SPY'].reindex(calendar),benchmark_series['QQQ'].reindex(calendar),ecfg,cfg,
                                     actions=[],security_id=sid)
    feature['date']=calendar.date
    feature['symbol']=symbol;feature['security_id']=sid;feature['feature_version']=FEATURE_VERSION
    feature['computed_at']=pd.Timestamp(receipt['retrieved_at'])
    feature['price_basis']='raw; no material action corrections installed'
    feature['price_source_hash']=receipt['raw_sha256']
    feature=feature.loc[bars.close.notna()]
    feature=feature.reindex(columns=[*RESEARCH_COLUMNS['daily_features'],'security_id','price_basis','price_source_hash'])
    # Cross-sectional ranks stay unavailable: a one-security supplement cannot
    # invent a population ranking or certify a portfolio's terminal economics.
    version=digest({'parent':parent['source_version'],'price':receipt,'benchmarks':bench_receipt,
                    'config':file_hash(cfg_path),'installer':file_hash(Path(__file__))})
    target=root/'data/pit/construction/versions'/version
    target.mkdir(parents=True,exist_ok=True)
    if (target/'manifest.json').exists():
        with HistoricalDatabase(target):
            return target
    shutil.copyfile(parent_dir/'historical.duckdb',target/'historical.duckdb')
    with duckdb.connect(str(target/'historical.duckdb')) as c:
        c.register('new_prices',frame)
        c.execute('INSERT INTO accepted_price SELECT * FROM new_prices')
        c.execute('INSERT INTO raw_price_hit SELECT security_id,symbol,date FROM new_prices')
        c.register('new_features',feature.reset_index(drop=True))
        c.execute('CREATE TABLE supplemental_features AS SELECT * FROM new_features')
        c.execute('INSERT INTO feature_presence SELECT security_id,symbol,date,tradability_pass FROM new_features')
        c.execute("""INSERT INTO evidence_graph SELECT 'security:'||security_id,'price-series:'||security_id||':raw','raw_price_series',
            min(date),max(date),NULL,'verified historical symbol-asof source',?,?,'accepted_verified_interval'
            FROM new_prices GROUP BY security_id""",[receipt['source_version'],receipt['raw_sha256']])
        c.execute('CHECKPOINT')
    for name in ('rules.json','dividends.json','identity-resolution.json'):
        if (parent_dir/name).exists():shutil.copyfile(parent_dir/name,target/name)
    manifest={**parent,'source_version':version,'database_sha256':file_hash(target/'historical.duckdb'),
        'parent_version':parent['source_version'],'parent_database_sha256':parent['database_sha256'],
        'price_supplement':{'security_id':sid,'rows':len(frame),'features':len(feature),'source':receipt,'benchmark_source':bench_receipt,
            'config_sha256':file_hash(cfg_path),'formula_version':FEATURE_VERSION,'installer_sha256':file_hash(Path(__file__)),
            'limitations':['cross-sectional ranks not recomputed','material/terminal economics remain disabled','does not change root native features']},
        'counts':{**parent['counts'],'accepted_price':parent['counts']['accepted_price']+len(frame),
                  'raw_price_hit':parent['counts']['raw_price_hit']+len(frame),'evidence_graph':parent['counts']['evidence_graph']+1}}
    if file_hash(parent_dir/'historical.duckdb')!=parent['database_sha256']:
        raise ValueError('parent changed during supplement')
    (target/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    temporary=pointer.with_suffix('.tmp')
    temporary.write_text(json.dumps({'directory':str(target.resolve()),'source_version':version},ensure_ascii=False,indent=2),encoding='utf-8')
    temporary.replace(pointer)
    print(json.dumps({'directory':str(target),'security_id':sid,'price_rows':len(frame),'feature_rows':len(feature)}))
    return target


if __name__=='__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--security-id',required=True);p.add_argument('--symbol',required=True)
    p.add_argument('--start',type=lambda v:pd.Timestamp(v).date(),required=True)
    p.add_argument('--end',type=lambda v:pd.Timestamp(v).date(),required=True)
    p.add_argument('--asof',type=lambda v:pd.Timestamp(v).date(),required=True)
    a=p.parse_args()
    if a.start>a.end or a.asof<a.end:raise ValueError('invalid historical request dates')
    supplement(Path.cwd(),a.security_id,a.symbol,a.start,a.end,a.asof)

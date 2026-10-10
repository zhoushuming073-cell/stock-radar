"""Read-only real local-bar parity and frozen receipt verification, NOT Cloud."""
from dataclasses import asdict
import importlib
import json
from pathlib import Path
import sys

import duckdb
import pandas as pd
from radar.research.high_beta.channel import analyze,settings
from radar.research.high_beta.cloud.build import prepare,sha
from radar.research.high_beta.cloud.data import QcEvidence
from radar.research.quant_lean import verify_freeze


def main():
    root=Path(__file__).resolve().parents[1];out=root/'data/research/q2-v12-cloud-exploratory'
    manifest=prepare(root,out);sys.path.insert(0,str(out/'upload'))
    cloud=importlib.import_module('sr_q2')
    # Known/current symbols are QA fixtures only, NEVER the Cloud historical pool.
    symbols=['AMBA','SOFI','APLD','RIOT','IONQ','IREN','ACHR','AAPL','AMD','NVDA','TSLA','PLTR']
    with duckdb.connect(str(root/'data/market.duckdb'),read_only=True) as c:
        f=c.execute('''select symbol,date,open,high,low,close,volume from daily_bars
            where symbol in (select unnest(?)) and date between '2024-01-01' and '2025-12-31'
            order by symbol,date''',[symbols+['SPY','QQQ']]).df()
    refs={s:f.loc[f.symbol.eq(s),['date','close']].reset_index(drop=True) for s in ['SPY','QQQ']}
    count=0;bars=0;qualified=0;cfg=settings(root)
    for symbol in symbols:
        x=f.loc[f.symbol.eq(symbol)].drop(columns='symbol').tail(430).reset_index(drop=True)
        if len(x)<cfg.min_daily_bars:raise ValueError('Real QA fixture unavailable; no synthetic fallback')
        day=str(x.date.iloc[-1].date());proof=QcEvidence(True,True,True)
        a=analyze(x,day,refs['SPY'],refs['QQQ'],proof,cfg)
        b=cloud.analyze(x,day,refs['SPY'],refs['QQQ'],proof,cloud.Settings(**asdict(cfg)))
        if a!=b:raise ValueError('Generated selector mathematical drift')
        count+=1;bars+=len(x);qualified+=int(a['market_qualified'])
    freeze=root/'data/research/quant-research-v1/freeze.json'
    if not freeze.exists():raise ValueError('Frozen parent receipt missing')
    old=json.loads(freeze.read_text(encoding='utf-8'));verify_freeze(root,old)
    result={'status':'PASS_LOCAL_SOURCE_PARITY_NOT_CLOUD','real_local_fixture_symbols':count,
        'real_local_fixture_bars':bars,'fixture_market_qualified':qualified,
        'input_hash':sha(pd.util.hash_pandas_object(f,index=False).values.tobytes()),
        'source_receipt':manifest['receipt']['selector_sha256'],
        'frozen_parent_receipt_sha256':sha(freeze.read_bytes()),'parent_freeze_verified':True,
        'qc_data_or_cloud_runtime_verified':False,
        'limitation':'Local vendor OHLCV used only to compare same math; not QC data parity or Cloud execution.'}
    (out/'local-parity.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))


if __name__=='__main__':main()

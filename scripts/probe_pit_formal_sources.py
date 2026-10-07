"""Run-scoped source discovery; every downloaded price remains quarantined."""
from collections import Counter
import gzip
import io
import json
from pathlib import Path
import re

import pandas as pd

from radar.pit.public_prices import query
from radar.pit.sources import git

PIN='vt6qeesk27k07492k5jc5b7p04mf0s6o'


def main():
    root=Path.cwd();out=root/'data/pit/clearance';cache=root/'data/pit/raw/clearance'
    inventory=json.loads((out/'iteration-0/blocker-inventory.json').read_text(encoding='utf-8'))
    ref_pin='a3eb36f951f9796c60c0a4c6bb70f13e50d9da6b';repo=root/'data/pit/raw/ticker-reference-data.git'
    reference=json.loads(git(repo,'show',ref_pin+':data/ticker_changes.json'))
    tickers=pd.read_csv(io.BytesIO(gzip.decompress(git(repo,'show',ref_pin+':history/float/tickers.csv.gz'))))
    candidates=dict(zip(tickers.ticker,tickers.cik))
    tiers=[]
    for row in inventory['rows']:
        cik=sorted({f'{int(candidates[s]):010d}' for s in row['symbols'] if s in candidates and pd.notna(candidates[s])}
                   | {f"{int(reference[s]['cik']):010d}" for s in row['symbols'] if isinstance(reference.get(s),dict) and reference[s].get('cik')})
        tier=row['identity_stratum']
        if len(cik)>1: tier='G'
        elif cik and tier=='F':
            active=any(m['valid_to'] and m['valid_to'][:10]>='2026-10-07' for m in row['symbol_intervals'])
            tier='A' if active else 'B'
        tiers.append({'security_id':row['security_id'],'candidate_stratum':tier,'cik_candidates':cik,
            'source_version':ref_pin,'certified':row['identity_status']=='verified',
            'decision':'secondary undated CIK/name discovery only; not historical share-class certification'})
    (out/'identity-tiers.json').write_text(json.dumps({'tier_counts':dict(Counter(r['candidate_stratum'] for r in tiers)),
        'source_url':'https://github.com/Quant-Lodge/ticker-reference-data','source_version':ref_pin,
        'license':'unverified, retained locally','rows':tiers},indent=2),encoding='utf-8')
    targets=[r for r in inventory['rows'] if r['no_price_category']]
    symbols=sorted({s for r in targets for s in r['symbols'] if re.fullmatch('[A-Z0-9.-]{1,20}',s)})
    metadata={};receipts=[];failures=[]
    for offset in range(0,len(symbols),40):
        selected=symbols[offset:offset+40]
        sql=f"SELECT * FROM symbol AS OF '{PIN}' WHERE act_symbol IN ("+','.join("'"+s+"'" for s in selected)+") ORDER BY act_symbol LIMIT 100"
        try:
            rows,receipt=query(sql,cache);receipts.append(receipt)
            for r in rows:metadata[r['act_symbol']]=r
        except (ValueError,OSError) as e:failures.append({'stage':'symbol','symbols':selected,'error':str(e)})
        print(json.dumps({'symbol_metadata_checked':min(offset+40,len(symbols)),'total':len(symbols)}),flush=True)
    # Probe three *missing* labels per identity, including vanished and reused names.
    # A probe is discovery, not full series acquisition or price acceptance.
    probes=[];prices=[]
    for offset in range(0,len(targets),12):
        batch=targets[offset:offset+12];conditions=[]
        for r in batch:
            d=r['missing_sessions'];dates=sorted({d[0],d[len(d)//2],d[-1]})
            for s in r['symbols']:
                if re.fullmatch('[A-Z0-9.-]{1,20}',s):
                    conditions.append("(act_symbol='"+s+"' AND date IN ("+','.join("'"+x+"'" for x in dates)+"))")
            probes.append({'security_id':r['security_id'],'symbols':r['symbols'],'missing_dates_probed':dates})
        sql=f"SELECT * FROM ohlcv AS OF '{PIN}' WHERE "+' OR '.join(conditions)+' ORDER BY date,act_symbol LIMIT 100'
        try:
            rows,receipt=query(sql,cache);receipts.append(receipt);prices.extend(rows)
        except (ValueError,OSError) as e:failures.append({'stage':'ohlcv','security_ids':[r['security_id'] for r in batch],'error':str(e)})
        if offset%120==0:print(json.dumps({'unpriced_probed':min(offset+12,len(targets)),'total':len(targets)}),flush=True)
    by_pair={(r['act_symbol'],r['date']) for r in prices}
    for r in probes:
        r['dolt_symbol_records']=[metadata[s] for s in r['symbols'] if s in metadata]
        r['source_prices_found']=sum(any((s,d) in by_pair for s in r['symbols']) for d in r['missing_dates_probed'])
        r['decision']='quarantined_identity_basis_action_scope_unreviewed'
        r['absence_meaning']='absent on sampled labels does not prove delisting or absence over the entire range'
    result={'dependency':inventory['dependency'],'source_url':'https://www.dolthub.com/repositories/post-no-preference/stocks',
        'source_version':PIN,'license':'CC-BY-SA-4.0; pinned LICENSE previously captured',
        'price_basis':'unverified discovery','accepted_prices':0,'security_probes':len(probes),
        'securities_with_price_probe':sum(r['source_prices_found']>0 for r in probes),
        'sample_bars':len(prices),'symbol_records':len(metadata),'failures':failures,'receipts':receipts,'rows':probes}
    (out/'unpriced-source-probes.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    (cache/'unpriced-probe-bars.json').write_text(json.dumps(prices,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in result.items() if k not in {'rows','receipts','failures'}}),flush=True)


if __name__=='__main__':main()

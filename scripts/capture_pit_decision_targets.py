"""Capture named P0 issuer documents and a two-symbol raw execution-gap probe."""
from concurrent.futures import ThreadPoolExecutor
from datetime import date,datetime,timezone
import hashlib
import json
from pathlib import Path

import requests

from radar.daily_update import credentials
from radar.config import load_settings
from radar.providers.alpaca import AlpacaProvider

TARGETS=[
    {'symbol':'TEM','first_trading':'2024-06-14','available_on':'2024-06-14',
     'url':'https://www.tempus.com/news/pr/tempus-announces-pricing-of-initial-public-offering/',
     'required_text':['initial public offering','June 14, 2024','TEM'],'classification':'new_listed_class'},
    {'symbol':'LINE','first_trading':'2024-07-25','available_on':'2024-07-25',
     'url':'https://ir.onelineage.com/press-releases/news-details/2024/Lineage-Announces-Pricing-of-Initial-Public-Offering/default.aspx',
     'required_text':['initial public offering','July 25, 2024','LINE'],'classification':'new_listed_class'},
    {'symbol':'SW','first_trading':'2024-07-08','available_on':'2024-07-09',
     'url':'https://investors.smurfitwestrock.com/regulatory-news/news-details/2024/COMPLETION-OF-LISTING/default.aspx',
     'required_text':['8 July 2024','ordinary shares','SW'],'classification':'new_combined_company_shares'},
    {'symbol':'FUN','first_trading':'2024-07-02','available_on':'2024-07-02',
     'url':'https://www.sec.gov/Archives/edgar/data/1999001/000119312524173290/d818752dex991.htm',
     'required_text':['July 2, 2024','common stock','CopperSteel'],'classification':'new_combined_company_shares'},
    {'symbol':'GAP','effective':'2024-08-22','available_on':'2024-08-09',
     'url':'https://www.gapinc.com/en-us/articles/2024/08/gap-inc-to-change-ticker-symbol-to-gap%E2%80%9D-on-august-',
     'required_text':['August 22, 2024','CUSIP','GPS'],'classification':'rename_continuity_evidence_only'}]


def main():
    root=Path.cwd();out=root/'data/pit/research-final/target-evidence';out.mkdir(exist_ok=True)
    cache=out/'raw';cache.mkdir(exist_ok=True)
    def capture(target):
        stamp=datetime.now(timezone.utc).isoformat()
        try:
            response=requests.get(target['url'],timeout=(10,30),headers={'User-Agent':'StockRadar research source audit contact local user'})
            raw=response.content;sha=hashlib.sha256(raw).hexdigest();(cache/(sha+'.raw')).write_bytes(raw)
            okay=response.status_code==200 and all(t.lower() in response.text.lower() for t in target['required_text'])
            return {**target,'http_status':response.status_code,'sha256':sha,'path':str((cache/(sha+'.raw')).resolve()),
                'captured_at':stamp,'accepted_for_rank_proof':okay,'license':'issuer document local evidence only; no raw redistribution'}
        except requests.RequestException as exc:
            return {**target,'captured_at':stamp,'accepted_for_rank_proof':False,'failure_type':type(exc).__name__}
    receipt=out/'issuer-documents.json'
    if not receipt.exists():
        with ThreadPoolExecutor(max_workers=5) as pool:docs=list(pool.map(capture,TARGETS))
        receipt.write_text(json.dumps(docs,indent=2),encoding='utf-8')
    else:docs=json.loads(receipt.read_text())
    prices=out/'raw-alpaca-probe.json'
    if not prices.exists():
        key,secret=credentials(root);provider=AlpacaProvider.from_credentials(key,secret)
        provider.max_attempts=2
        settings=load_settings(root)
        result=[];failed=[]
        for batch in provider.get_daily_bars(['CLSK','SMR'],date(2024,11,4),date(2024,12,24),settings.feed,'raw'):
            result.extend(b.model_dump(mode='json') for b in batch.bars);failed.extend(batch.failed_symbols)
        prices.write_text(json.dumps({'provider':'Alpaca','feed':settings.feed,'adjustment':'raw','bars':result,
            'failed_symbols':failed,'license':'existing user account local research; no raw redistribution',
            'status':'independent raw probe; no implicit source installation or fallback',
            'captured_at':datetime.now(timezone.utc).isoformat()},indent=2,default=str),encoding='utf-8')
    print(json.dumps({'documents':[{k:d.get(k) for k in ['symbol','http_status','accepted_for_rank_proof']} for d in docs],
                     'probe_bars':len(json.loads(prices.read_text())['bars'])},indent=2),flush=True)


if __name__=='__main__':main()

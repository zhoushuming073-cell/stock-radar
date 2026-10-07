"""Read-only, cached source benchmarks. Discovery never installs PIT data.

Use the exact frozen closure; ticker/date hits are candidates, not identities.
Raw downloads stay under ignored data/pit/raw/source-breakthrough.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
import csv
from datetime import datetime, timezone
import hashlib
import json
import io
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request

from radar.pit.builder import digest


class Cache:
    def __init__(self, path):
        self.path = Path(path)
        self.path.mkdir(parents=True, exist_ok=True)

    def get(self, url, *, body=None, max_bytes=40_000_000):
        key = digest({'url': url, 'body': body.decode() if body else None})
        index = self.path / (key + '.json')
        if index.exists():
            receipt = json.loads(index.read_text(encoding='utf-8'))
            raw = (self.path / (receipt['sha256'] + '.raw')).read_bytes()
            if hashlib.sha256(raw).hexdigest() != receipt['sha256']:
                raise ValueError('source cache mutated')
            if receipt['url'] != url or len(raw) != receipt['bytes']:
                raise ValueError('source receipt mismatched')
            if len(raw) > max_bytes:
                raise ValueError('cached source exceeds download bound')
            if receipt['status'] is not None:
                return raw, receipt
            # Retain failed receipts before an explicit subsequent benchmark retry.
            suffix = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')
            index.rename(self.path / (key + '-' + suffix + '.failed.json'))
        request = urllib.request.Request(url, data=body, headers={
            'User-Agent': 'StockRadarPIT research https://github.com/zhoushuming073-cell/stock-radar',
            **({'Content-Type': 'application/json'} if body else {})})
        status, error = None, None
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                status = response.status
                raw = response.read(max_bytes + 1)
                final_url = response.url
        except urllib.error.HTTPError as e:
            raw = e.read(max_bytes + 1); status = e.code; error = str(e); final_url = url
        except (OSError, TimeoutError) as e:
            raw = str(e).encode(); error = str(e); final_url = url
        if len(raw) > max_bytes:
            raise ValueError('source exceeds bounded download; not cached as complete')
        sha = hashlib.sha256(raw).hexdigest()
        receipt = {'url': url, 'final_url': final_url, 'status': status, 'error': error,
                   'sha256': sha, 'bytes': len(raw), 'captured_at': datetime.now(timezone.utc).isoformat()}
        (self.path / (sha + '.raw')).write_bytes(raw)
        index.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
        return raw, receipt

    def json(self, url, **kwargs):
        raw, receipt = self.get(url, **kwargs)
        if receipt['status'] != 200:
            raise ValueError('source access failed: ' + str(receipt['status']))
        return json.loads(raw), receipt

    def sql(self, owner, repo, branch, sql):
        url = f'https://www.dolthub.com/api/v1alpha1/{owner}/{repo}/{branch}?'
        payload, receipt = self.json(url + urllib.parse.urlencode({'q': sql}))
        if payload.get('query_execution_status') != 'Success' or payload.get('sql_query') != sql or not isinstance(payload.get('rows'), list):
            raise ValueError('Dolt response failed/truncated/query mismatched')
        return payload['rows'], receipt


def candidate_price_coverage(manifest, by_date):
    """Count each missing identity/date once; retain ticker ambiguity separately."""
    rows = []
    for record in manifest['dependencies'] + manifest['benchmarks']:
        symbols = set(record.get('symbols', [record.get('symbol')])) - {None}
        found = [d for d in record['missing_sessions'] if symbols & by_date.get(d, set())]
        # Even a dated observed mapping is not necessarily a verified issuer/class.
        in_observed = [d for d in found if any(m['symbol'] in by_date.get(d, set())
            and m['valid_from'][:10] <= d <= (m['valid_to'] or '9999-12-31')[:10]
            for m in record.get('mappings', []))]
        rows.append({'security_id':record.get('security_id', record.get('symbol')), 'missing':len(record['missing_sessions']),
            'ticker_date_hits':len(found), 'inside_observed_mapping':len(in_observed),
            'found_sessions':found, 'accepted_prices':0,
            'decision':'quarantine; identity/license/raw basis/full action proof not inferred'})
    total = sum(r['missing'] for r in rows); hits = sum(r['ticker_date_hits'] for r in rows)
    return {'missing_before':total, 'source_exists':hits, 'candidate_remaining':total-hits,
            'inside_observed_mapping':sum(r['inside_observed_mapping'] for r in rows),
            'identity_safe_accepted':0, 'formal_missing_after':total, 'rows':rows}


def dolt_benchmark(root, manifest, cache):
    pin = 'vt6qeesk27k07492k5jc5b7p04mf0s6o'
    records = manifest['dependencies'] + manifest['benchmarks']
    dates = sorted({d for r in records for d in r['missing_sessions']})
    by_date, receipts = {}, []
    needed=defaultdict(set)
    for record in records:
        for day in record['missing_sessions']:
            needed[day].update(record.get('symbols', [record['symbol']] if 'symbol' in record else []))
    # The source primary key begins with date. One dated aggregate row avoids
    # ticker-range scans, per-security IO, and the public API's row truncation.
    def fetch(offset):
        batch = dates[offset:offset+1]
        symbols=','.join("'"+s.replace("'","''")+"'" for s in sorted(needed[batch[0]]))
        sql = f"SELECT '{batch[0]}' AS date,JSON_ARRAYAGG(act_symbol) AS symbols FROM ohlcv AS OF '{pin}' WHERE date='{batch[0]}' AND act_symbol IN ({symbols}) LIMIT 2"
        rows, receipt = cache.sql('post-no-preference','stocks','master',sql)
        seen = set()
        for r in rows:
            if r['date'] not in batch or r['date'] in seen:
                raise ValueError('unexpected/duplicate Dolt session response')
            seen.add(r['date'])
            values = json.loads(r['symbols']) if isinstance(r['symbols'],str) else r['symbols']
            if values is None:values=[]
            if not isinstance(values,list) or not all(isinstance(s,str) for s in values):
                raise ValueError('invalid symbol aggregate')
            r['symbols']=values
            seen.add(r['date'])
        if seen != set(batch):
            raise ValueError('partial Dolt session response')
        return rows,receipt
    with ThreadPoolExecutor(max_workers=2) as pool:
        for i,(rows,receipt) in enumerate(pool.map(fetch,range(len(dates)))):
            for r in rows:
                values=json.loads(r['symbols']) if isinstance(r['symbols'],str) else r['symbols']
                by_date[r['date']]=set(values)
            receipts.append(receipt)
            if i%20==0 or i+1==len(dates):print('Dolt missing labels',i+1,'/',len(dates),flush=True)
    result = candidate_price_coverage(manifest,by_date)
    result.update({'source':'Dolt stocks','pin':pin,'queried_sessions':len(dates),'receipts':receipts})
    out = root/'data/pit/source-breakthrough/dolt-full-coverage.json'
    out.write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def reference_benchmark(root,manifest,cache):
    pins=json.loads((root/'data/pit/source-breakthrough/git-history-pins.json').read_text(encoding='utf-8'))
    def fetch(item):
        source,record=item
        file='mappings/stocks/mappings.csv' if source=='cik' else 'data/nasdaq-listed.csv'
        repo='jadchaar/sec-cik-mapper' if source=='cik' else 'datasets/nasdaq-listings'
        raw,receipt=cache.get(f'https://raw.githubusercontent.com/{repo}/{record["sha"]}/{file}')
        if receipt['status']!=200:raise ValueError('reference fetch failed')
        rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        required={'CIK','Ticker','Name','Exchange'} if source=='cik' else {'Symbol','Security Name'}
        if not rows or not required<=rows[0].keys():raise ValueError('reference payload schema')
        return source,{**record,'rows':rows,'receipt':receipt}
    jobs=[(source,r) for source in ('cik','nasdaq') for r in pins[source]]
    snapshots=defaultdict(list)
    with ThreadPoolExecutor(max_workers=4) as pool:
        for source,record in pool.map(fetch,jobs):snapshots[source].append(record)
    for snapshot in snapshots['cik']:
        snapshot['by_symbol']=defaultdict(list)
        for row in snapshot['rows']:snapshot['by_symbol'][row['Ticker']].append(row)
    candidates=[]
    for d in manifest['dependencies']:
        hits=[]
        for snapshot in snapshots['cik']:
            date=snapshot['date'][:10]
            for symbol in d['symbols']:
              for r in snapshot['by_symbol'].get(symbol,[]):
                if any(m['symbol']==r['Ticker'] and
                     m['valid_from'][:10]<=date<=(m['valid_to'] or '9999-12-31')[:10] for m in d['mappings']):
                    hits.append({'date':date,'ticker':r['Ticker'],'cik':r['CIK'],'name':r['Name'],
                                 'exchange':r['Exchange'],'snapshot':snapshot['sha']})
        candidates.append({'security_id':d['security_id'],'dated_issuer_candidates':hits,
            'ciks':sorted({h['cik'] for h in hits}), 'verified':False,
            'decision':'dated issuer evidence only; common share class, reuse and interval completeness unproven'})
    # Whole Validation comparison against an independent Nasdaq symbol directory.
    # Never carry a monthly snapshot into PIT input; age is reported for comparison only.
    comparisons=[]
    ids={d['security_id']:d for d in manifest['dependencies']}
    for p in manifest['population']:
        date=p['date'];available=[s for s in snapshots['nasdaq'] if s['date'][:10]<=date]
        if not available:
            comparisons.append({'date':date,'status':'no_prior_snapshot'});continue
        s=max(available,key=lambda x:x['date']);a=set()
        for sid in p['security_ids']:
            for m in ids[sid]['mappings']:
                if m['exchange']=='NASDAQ' and m['valid_from'][:10]<=date<=(m['valid_to'] or '9999-12-31')[:10]:a.add(m['symbol'])
        b={r['Symbol'] for r in s['rows'] if not r['Symbol'].startswith('File Creation')}
        comparisons.append({'date':date,'status':'comparison_only','snapshot':s['sha'],
            'snapshot_date':s['date'][:10],'age_days':(datetime.fromisoformat(date)-datetime.fromisoformat(s['date'][:10])).days,
            'current_eligible_nasdaq':len(a),'directory_all_instruments':len(b),
            'intersection':len(a&b),'current_only':sorted(a-b),'directory_only':sorted(b-a),
            'note':'directory includes non-common classes; monthly age cannot certify daily membership'})
    result={'identity':{'snapshot_count':len(snapshots['cik']),
        'dated_candidate_ids':sum(bool(r['dated_issuer_candidates']) for r in candidates),
        'multiple_cik_candidates':sum(len(r['ciks'])>1 for r in candidates),
        'formal_verified':0,'rows':candidates}, 'membership':{'snapshot_count':len(snapshots['nasdaq']),
        'daily_comparisons':comparisons,'formal_membership':'FAIL'},
        'receipts':{k:[{x:v for x,v in s.items() if x not in {'rows','by_symbol'}} for s in values] for k,values in snapshots.items()}}
    (root/'data/pit/source-breakthrough/reference-coverage.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dolt',action='store_true')
    p.add_argument('--reference',action='store_true')
    a=p.parse_args();root=Path.cwd()
    entry=json.loads((root/'data/pit/source-breakthrough/entry-receipt.json').read_text(encoding='utf-8'))
    ref=entry['dependency'];raw=Path(ref['path']).read_bytes()
    if hashlib.sha256(raw).hexdigest()!=ref['sha256']:
        raise ValueError('frozen dependency mutated')
    manifest=json.loads(raw);cache=Cache(root/'data/pit/raw/source-breakthrough')
    if a.dolt:
        result=dolt_benchmark(root,manifest,cache)
        print(json.dumps({k:v for k,v in result.items() if k not in {'rows','receipts'}}))
    if a.reference:
        result=reference_benchmark(root,manifest,cache)
        print({k:{x:v for x,v in value.items() if x not in {'rows','daily_comparisons'}} for k,value in result.items() if k!='receipts'})


if __name__=='__main__':main()

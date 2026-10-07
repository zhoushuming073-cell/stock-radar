"""Small public source probes and OTC scope comparison; never accepts data."""
import csv
import hashlib
import io
import json
from pathlib import Path

from benchmark_pit_sources import Cache

CASES = ['META','FB','NVDA','ATVI','TWTR','SPLK','BBBY','BYON','IREN','AAPL','LEHMQ']


def main():
    root = Path.cwd()
    cache = Cache(root/'data/pit/raw/source-breakthrough')
    entry = json.loads((root/'data/pit/source-breakthrough/entry-receipt.json').read_text())
    raw_manifest = Path(entry['dependency']['path']).read_bytes()
    if hashlib.sha256(raw_manifest).hexdigest() != entry['dependency']['sha256']:
        raise ValueError('frozen dependency mutated')
    manifest = json.loads(raw_manifest)
    required_days = [day for record in manifest['dependencies'] + manifest['benchmarks']
                     for day in record['required_sessions']]
    start, end = min(required_days), max(required_days)
    output = {'cik_cases': [], 'dolt_history': {}, 'finra': {}}
    pins = json.loads((root/'data/pit/source-breakthrough/cik-case-pins.json').read_text())
    for p in pins:
        raw, receipt = cache.get(f'https://raw.githubusercontent.com/jadchaar/sec-cik-mapper/{p["sha"]}/mappings/stocks/mappings.csv')
        if receipt['status'] != 200: raise ValueError('CIK case access failed')
        rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        output['cik_cases'].append({**p, 'receipt':receipt,
            'rows':[r for r in rows if r['Ticker'] in CASES]})
    pin = '6qi9hbcfdn0ng3ths48mgudsisk8nkhh'
    sql = f"SELECT * FROM stock_history AS OF '{pin}' LIMIT 3"
    try:
        rows, receipt = cache.sql('graziek9','Stock_Data','main',sql)
        output['dolt_history'] = {'pin':pin, 'rows':rows, 'receipt':receipt}
    except Exception as e: output['dolt_history'] = {'pin':pin,'error':str(e)}
    # Documented read-only query API. Bounded pagination, validate every returned
    # publication date; absence is never interpreted as a no-action certificate.
    url = 'https://api.finra.org/data/group/otcMarket/name/OTCDAILYLIST'
    all_rows, receipts = [], []
    for page in range(40):
        body = json.dumps({'limit':5000,'offset':page*5000,
            'fields':['OTCDailyListID','calendarDay','exDate','dailyListDatetime','oldSymbolCode','newSymbolCode',
                'oldClassText','newClassText','dailyListReasonDescription','dailyListEventCode',
                'forwardSplitRate','reverseSplitRate','cashAmountText','securityAddFlag','securityDeleteFlag'],
            'dateRangeFilters':[{'fieldName':'calendarDay',
            'startDate':start,'endDate':end}]}).encode()
        raw, receipt = cache.get(url, body=body)
        receipts.append(receipt)
        if receipt['status'] != 200: raise ValueError('FINRA bounded query access failed')
        rows = list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
        if rows and 'calendarDay' not in rows[0]: raise ValueError('FINRA schema failed')
        if any(None in r or None in r.values() for r in rows):raise ValueError('FINRA malformed CSV')
        if any(not start <= r['calendarDay'] <= end for r in rows):
            raise ValueError('FINRA date filter ignored')
        all_rows.extend(rows)
        print('FINRA page',page,'rows',len(rows),flush=True)
        if len(rows)<5000: break
    else: raise ValueError('FINRA bounded pagination incomplete')
    ids = [r['OTCDailyListID'] for r in all_rows]
    if len(ids)!=len(set(ids)): raise ValueError('FINRA overlapping pages/mutated source')
    by_symbol = {}
    for r in all_rows:
        for s in {r['oldSymbolCode'],r['newSymbolCode']} - {''}:
            by_symbol.setdefault(s,[]).append(r)
    candidates = []
    for d in manifest['dependencies']:
        events = {r['OTCDailyListID']:r for s in d['symbols'] for r in by_symbol.get(s,[])}
        dated = [r for r in events.values() if min(d['required_sessions']) <= r['calendarDay'] <= max(d['required_sessions'])
                 and any(m['symbol'] in {r['oldSymbolCode'],r['newSymbolCode']}
                 and m['valid_from'][:10] <= r['calendarDay'] <= (m['valid_to'] or '9999-12-31')[:10]
                 for m in d['mappings'])]
        if events: candidates.append({'security_id':d['security_id'],'ticker_event_hits':len(events),
            'dated_candidate_hits':len(dated),'event_ids':sorted(events), 'accepted_scopes':0})
    output['finra'] = {'publication_scope':[start,end],
        'rows':len(all_rows),'pages':len(receipts),'receipts':receipts,
        'candidate_ids':len(candidates),'dated_candidate_ids':sum(r['dated_candidate_hits']>0 for r in candidates),
        'candidates':candidates,'cases':{s:by_symbol.get(s,[]) for s in CASES},
        'certified_scopes':0,'note':'OTC events, publication dates; not US listed scope completeness or identity certification'}
    (root/'data/pit/source-breakthrough/bulk-reference-samples.json').write_text(json.dumps(output,indent=2))
    print({k:v for k,v in output['finra'].items() if k not in {'candidates','cases','receipts'}})


if __name__=='__main__':main()

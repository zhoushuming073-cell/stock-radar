"""Download immutable raw OHLC for the whole frozen closure, without installing it.

One JSON aggregate per session avoids DoltHub's row cap. Expected row count is
returned independently and checked; an incomplete response is never accepted.
Cached failed requests and their source bytes remain inspectable.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import datetime
import json
from pathlib import Path

from benchmark_pit_sources import Cache
from radar.pit.builder import digest
from radar.pit.features import file_hash


def parse_aggregate(rows, day, symbols):
    if len(rows) != 1 or rows[0].get('date') != day:
        raise ValueError('unexpected aggregate session')
    row = rows[0]
    values = json.loads(row['bars']) if isinstance(row['bars'], str) else row['bars']
    values = values or []
    if not isinstance(values, list) or len(values) != int(row['n']):
        raise ValueError('truncated aggregate')
    seen = set()
    for value in values:
        if len(value) != 6 or (symbols is not None and value[0] not in symbols) or value[0] in seen:
            raise ValueError('duplicate/unrequested source ticker')
        seen.add(value[0])
    return values


def main():
    root = Path.cwd()
    out = root/'data/pit/research-grade'
    out.mkdir(parents=True, exist_ok=True)
    rules_path = root/'config/pit_research_grade_rules.json'
    rules = json.loads(rules_path.read_text(encoding='utf-8'))
    entry = json.loads((root/'data/pit/source-breakthrough/entry-receipt.json').read_text())
    reference = entry['dependency']
    if file_hash(Path(reference['path'])) != reference['sha256']:
        raise ValueError('frozen closure changed')
    manifest = json.loads(Path(reference['path']).read_text())
    frozen = {'rules_sha256': file_hash(rules_path), 'rules': rules,
              'dependency': reference, 'selection': 'whole closure, independent of identity acceptance or returns'}
    path = out/'rules-freeze.json'
    if path.exists() and json.loads(path.read_text()) != frozen:
        raise ValueError('research rules changed after freeze')
    path.write_text(json.dumps(frozen, indent=2), encoding='utf-8')
    needed = defaultdict(set)
    for record in manifest['dependencies'] + manifest['benchmarks']:
        for day in record['required_sessions']:
            needed[day].update(record.get('symbols', [record.get('symbol')]))
    cache = Cache(root/'data/pit/raw/research-grade')
    pin = rules['prices']['source_version']
    def fetch(day):
        # Fetch a complete dated slice. An IN clause for 6k symbols exceeds
        # HTTP header limits; exact-date aggregation has the same index prefix.
        sql = (f"SELECT '{day}' AS date,COUNT(*) AS n,"
               "JSON_ARRAYAGG(JSON_ARRAY(act_symbol,open,high,low,close,volume)) AS bars "
               f"FROM ohlcv AS OF '{pin}' WHERE date='{day}' LIMIT 2")
        rows, receipt = cache.sql('post-no-preference', 'stocks', 'master', sql)
        bars = parse_aggregate(rows, day, None)
        if len(bars)>50000: raise ValueError('unexpected daily population exceeds bound')
        return day, {'date': day, 'rows': len(bars), 'receipt': receipt}
    receipts, failures = {}, {}
    with ThreadPoolExecutor(max_workers=2) as pool:
        jobs = {pool.submit(fetch, day): day for day in sorted(needed)}
        for i, job in enumerate(as_completed(jobs), 1):
            day = jobs[job]
            try:
                day, receipt = job.result(); receipts[day] = receipt
            except Exception as error:
                failures[day] = str(error)
            if i % 20 == 0 or i == len(jobs):
                print('Research raw sessions', i, '/', len(jobs), 'failures', len(failures), flush=True)
                (out/'download-progress.json').write_text(json.dumps({
                    'completed': i, 'total': len(jobs), 'failed': failures}, indent=2))
    source = {'policy': rules['policy'], 'pin': pin, 'license': rules['prices']['license'],
              'rules_sha256': frozen['rules_sha256'], 'dependency_sha256': manifest['dependency_sha256'],
              'sessions': sorted(receipts.values(), key=lambda x:x['date']), 'failures': failures,
              'complete': not failures, 'rows': sum(v['rows'] for v in receipts.values())}
    (out/'raw-price-receipts.json').write_text(json.dumps(source, indent=2), encoding='utf-8')
    # Material events and ordinary distributions are explicitly separate scans.
    start, end = min(needed), max(needed)
    for table, date_column in [('split','ex_date'), ('dividend','ex_date')]:
        sql = (f"SELECT COUNT(*) AS n,JSON_ARRAYAGG(JSON_OBJECT('symbol',act_symbol,'date',{date_column},"
               + ("'to_factor',to_factor,'for_factor',for_factor" if table=='split' else "'amount',amount")
               + f")) AS events FROM {table} AS OF '{pin}' WHERE {date_column} BETWEEN '{start}' AND '{end}' LIMIT 2")
        try:
            rows, receipt = cache.sql('post-no-preference','stocks','master',sql)
            values = rows[0]['events']; values = json.loads(values) if isinstance(values,str) else values
            values = values or []
            if len(rows)!=1 or len(values)!=int(rows[0]['n']): raise ValueError('truncated event aggregate')
            for event in values:
                event['date']=str(event['date'])[:10]
                datetime.strptime(event['date'],'%Y-%m-%d')
            payload = {'table':table,'events':values,'receipt':receipt,'source_version':pin,'coverage':[start,end]}
        except Exception as error:
            payload = {'table':table,'error':str(error),'source_version':pin,'coverage':[start,end]}
        (out/(table+'-scan.json')).write_text(json.dumps(payload,indent=2),encoding='utf-8')
    print('Raw downloaded', source['rows'], 'complete', source['complete'], flush=True)


if __name__ == '__main__':
    main()

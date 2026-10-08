"""Dated, pinned public reference observations; no current-list backfill."""
import argparse, csv, io, json
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
import pandas as pd
from radar.pit.sources import git, GitObjects, effective_day, pin
from radar.pit.builder import digest

def acquire(root, end):
    output=root/'data/pit/construction/references'
    output.mkdir(parents=True,exist_ok=True)
    sources=[('cik','cik-history.git','mappings/stocks/mappings.csv','jadchaar/sec-cik-mapper','SEC'),
             ('nasdaq','nasdaq-history.git','data/nasdaq-listed.csv','datasets/nasdaq-listings','NASDAQ')]
    frames=[]; evidence=[]; summaries=[]
    for kind,folder,path,repo,origin in sources:
        checkout=root/'data/pit/raw/database-construction'/folder
        commit=pin(checkout,date.fromisoformat(end))
        entries=[]
        for line in git(checkout,'log','--first-parent','--format=%H %cI',commit,'--',path).decode().splitlines():
            sha,stamp=line.split(' ',1);day=str(effective_day(stamp))
            if '2021-08-01'<=day<=end:entries.append((day,sha,stamp))
        months=defaultdict(list)
        for entry in sorted(entries):months[entry[0][:7]].append(entry)
        selected={e for group in months.values() for e in (group[0],group[-1])}
        # Daily issuer observations in the previous research interval remain useful.
        selected|={e for e in entries if '2024-09-01'<=e[0]<='2025-03-01'}
        objects=GitObjects(checkout)
        try:
            for day,sha,stamp in sorted(selected):
                raw=objects.read(sha+':'+path)
                if not raw:continue
                import hashlib
                h=hashlib.sha256(raw).hexdigest()
                target=output/(h+'.csv')
                if target.exists() and target.read_bytes()!=raw:raise ValueError('immutable reference bytes changed')
                if not target.exists():target.write_bytes(raw)
                rows=list(csv.DictReader(io.StringIO(raw.decode('utf-8-sig'))))
                ev={'source':kind,'origin':origin,'url':f'https://raw.githubusercontent.com/{repo}/{sha}/{path}',
                    'source_version':sha,'available_on':day,'available_at':stamp,'raw_sha256':h,
                    'raw_path':str(target),'rows':len(rows),'confidence':'dated observation; not full population attestation'}
                ev['retrieved_at']=datetime.fromtimestamp(target.stat().st_mtime,timezone.utc).isoformat()
                ev['availability_method']='Git committer timestamp; US close cutoff; source document may predate mirror commit'
                ev['license']='mirror MIT; upstream SEC disclosure separately attributed' if kind=='cik' else 'Nasdaq-derived mirror; upstream terms not inferred; raw retained locally'
                ev['evidence_id']=digest({k:ev[k] for k in ('source','source_version','raw_sha256','available_on')})
                evidence.append(ev)
                for r in rows:
                    symbol=r.get('Ticker',r.get('Symbol',''))
                    if not symbol or symbol.startswith('File Creation'):continue
                    frames.append({'symbol':symbol,'cik':str(r.get('CIK','')).zfill(10) if r.get('CIK') else '',
                        'name':r.get('Name',r.get('Security Name','')),'exchange':r.get('Exchange','NASDAQ').upper(),
                        'etf':r.get('ETF',''),'test_issue':r.get('Test Issue',''),'available_on':day,
                        'source':kind,'evidence_id':ev['evidence_id']})
        finally:objects.close()
        summaries.append({'source':kind,'origin':origin,'pin':commit,'snapshots':len(selected),
                          'first_available':min(e[0] for e in selected),'latest_available':max(e[0] for e in selected)})
    pd.DataFrame(frames).to_parquet(output/'observations.parquet',index=False)
    (output/'evidence.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(summaries,indent=2),encoding='utf-8')
    print(json.dumps({'sources':summaries,'observations':len(frames),'evidence':len(evidence)},indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--end',default='2026-10-07');a=p.parse_args()
    acquire(Path.cwd(),a.end)

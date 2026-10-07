"""Bounded range samples from public, revision-pinned Parquet; no installation."""
import hashlib
import io
import json
from pathlib import Path
import re
import urllib.request

import pyarrow.parquet as pq

CASES=['META','FB','NVDA','ATVI','TWTR','SPLK','BBBY','BYON','IREN','AAPL','LEHMQ']


class Ranges(io.RawIOBase):
    def __init__(self,url,cache,budget=30_000_000):
        if not re.search(r'/resolve/[0-9a-f]{40}/',url):raise ValueError('public sample needs immutable revision')
        self.url=url;self.cache=Path(cache);self.cache.mkdir(parents=True,exist_ok=True)
        self.pos=0;self.receipts=[];self.budget=budget;self.downloaded=0
        self.size=None;self.etag=None
        self._range(0,0)

    def readable(self):return True
    def seekable(self):return True
    def tell(self):return self.pos
    def seek(self,pos,whence=0):
        self.pos=pos if whence==0 else self.pos+pos if whence==1 else self.size+pos
        if not 0<=self.pos<=self.size:raise ValueError('invalid parquet seek')
        return self.pos

    def _range(self,start,end):
        if start < 0 or end < start:
            raise ValueError('invalid range')
        key=hashlib.sha256((self.url+f'#{start}:{end}').encode()).hexdigest()
        index=self.cache/(key+'.json')
        if index.exists():
            r=json.loads(index.read_text());raw=(self.cache/(r['sha256']+'.raw')).read_bytes()
            if hashlib.sha256(raw).hexdigest()!=r['sha256']:raise ValueError('range cache mutation')
        else:
            if self.downloaded+end-start+1>self.budget:raise ValueError('sample download budget exceeded')
            req=urllib.request.Request(self.url,headers={'Range':f'bytes={start}-{end}',
                'User-Agent':'StockRadarPIT source benchmark'})
            with urllib.request.urlopen(req,timeout=45) as response:
                if response.status!=206:raise ValueError('server ignored bounded range; no full download')
                cr=response.headers.get('Content-Range','');match=re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)',cr)
                if not match or tuple(map(int,match.groups()[:2]))!=(start,end):raise ValueError('range mismatch')
                raw=response.read(end-start+2)
                if len(raw)!=end-start+1:raise ValueError('partial range payload')
                r={'url':self.url,'start':start,'end':end,'size':int(match[3]),
                   'etag':response.headers.get('ETag'),'sha256':hashlib.sha256(raw).hexdigest()}
            (self.cache/(r['sha256']+'.raw')).write_bytes(raw);index.write_text(json.dumps(r,indent=2))
        if r['url'] != self.url or r['start'] != start or r['end'] != end or r['size'] <= end or len(raw) != end-start+1:
            raise ValueError('cached range metadata mismatched')
        if self.downloaded+len(raw)>self.budget:raise ValueError('sample download budget exceeded')
        if self.size is not None and (r['size']!=self.size or r['etag']!=self.etag):raise ValueError('source mutation')
        self.size=r['size'];self.etag=r['etag'];self.receipts.append(r);self.downloaded+=len(raw)
        return raw

    def read(self,n=-1):
        if n<0:n=self.size-self.pos
        n=min(n,self.size-self.pos)
        if not n:return b''
        raw=self._range(self.pos,self.pos+n-1);self.pos+=n;return raw


def main():
    root=Path.cwd();from benchmark_pit_sources import Cache
    c=Cache(root/'data/pit/raw/source-breakthrough')
    meta,_=c.json('https://huggingface.co/api/datasets/defeatbeta/yahoo-finance-data')
    url=f'https://huggingface.co/datasets/{meta["id"]}/resolve/{meta["sha"]}/data/US/stock_prices.parquet'
    reader=Ranges(url,root/'data/pit/raw/source-breakthrough-ranges')
    f=pq.ParquetFile(reader);groups=[];selected=[]
    names=f.schema.names;symbol=names.index('symbol')
    for i in range(f.metadata.num_row_groups):
        rg=f.metadata.row_group(i);stats=rg.column(symbol).statistics
        if stats and stats.has_min_max and any(stats.min<=s<=stats.max for s in CASES):groups.append(i)
    for i in groups:
        frame=f.read_row_group(i).to_pandas()
        subset=frame[frame.symbol.isin(CASES)]
        # Preserve an actual source observation near each case's relevant lifecycle.
        for s in sorted(set(subset.symbol)):
            rows=subset[subset.symbol==s].sort_values('report_date')
            within=rows[rows.report_date.astype(str).between('2021-01-01','2025-09-22')]
            selected.append({'symbol':s,'first':str(rows.report_date.min()),'last':str(rows.report_date.max()),
                'rows_in_group':len(rows),'scope_rows_in_group':len(within),
                'lifecycle_probes':json.loads(rows[rows.report_date.astype(str).isin(
                    ['2022-06-08','2023-04-28','2024-06-03','2025-09-22'])].to_json(orient='records')),
                'examples':json.loads(within.tail(2).to_json(orient='records'))})
    out={'source':'defeatbeta Yahoo','revision':meta['sha'],'file_size':reader.size,
        'schema':names,'total_rows':f.metadata.num_rows,'row_groups':f.metadata.num_row_groups,
        'selected_groups':groups,'downloaded_bytes':reader.downloaded,'samples':selected,
        'receipts':reader.receipts,'acceptance':'quarantine; publisher license claim does not establish upstream rights or dated class identity'}
    (root/'data/pit/source-breakthrough/defeatbeta-price-samples.json').write_text(json.dumps(out,indent=2))
    print({k:v for k,v in out.items() if k not in {'receipts','samples'}})
    print('sample symbols',sorted({r['symbol'] for r in selected}))


if __name__=='__main__':main()

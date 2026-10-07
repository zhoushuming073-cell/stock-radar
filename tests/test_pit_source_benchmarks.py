"""Research tools must reject incomplete or changed evidence and never accept aliases."""
import hashlib
import importlib.util
import json
from pathlib import Path

import pytest


def module(name):
    path = Path(__file__).resolve().parents[1]/'scripts'/(name+'.py')
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


bench = module('benchmark_pit_sources')
ranges = module('sample_pit_public_parquet')


def test_aliases_and_reuse_are_candidates_only():
    records = [dict(security_id='old',symbols=['OLD','NEW'],missing_sessions=['2024-01-02'],
        mappings=[dict(symbol='OLD',valid_from='2020-01-01',valid_to='2023-12-31')]),
        dict(security_id='new',symbols=['NEW'],missing_sessions=['2024-01-02'],
        mappings=[dict(symbol='NEW',valid_from='2024-01-01',valid_to=None)])]
    result = bench.candidate_price_coverage({'dependencies':records,'benchmarks':[]},
        {'2024-01-02':{'OLD','NEW'}})
    assert result['source_exists']==2  # identity/date, not three alias hits
    assert result['inside_observed_mapping']==1
    assert result['identity_safe_accepted']==0
    assert result['formal_missing_after']==2


def test_benchmark_single_symbol_schema_and_empty_scope():
    result = bench.candidate_price_coverage({'dependencies':[], 'benchmarks':[
        {'symbol':'SPY','missing_sessions':['2024-01-02']},
        {'symbol':'QQQ','missing_sessions':[]}]}, {'2024-01-02':{'SPY'}})
    assert result['source_exists']==1
    assert result['rows'][0]['security_id']=='SPY'
    assert result['inside_observed_mapping']==0
    assert result['formal_missing_after']==1


def test_cache_rejects_changed_raw(tmp_path):
    cache = bench.Cache(tmp_path)
    raw=b'original'; sha=hashlib.sha256(raw).hexdigest()
    (tmp_path/(sha+'.raw')).write_bytes(b'changed')
    key=bench.digest({'url':'https://source','body':None})
    (tmp_path/(key+'.json')).write_text(json.dumps({'sha256':sha}))
    with pytest.raises(ValueError,match='mutated'): cache.get('https://source')


@pytest.mark.parametrize('payload',[
    {'query_execution_status':'Error','sql_query':'q','rows':[]},
    {'query_execution_status':'Success','sql_query':'other','rows':[]},
    {'query_execution_status':'Success','sql_query':'q'},
])
def test_sql_rejects_partial_or_wrong_query(tmp_path,monkeypatch,payload):
    cache=bench.Cache(tmp_path)
    monkeypatch.setattr(cache,'json',lambda *a,**kw:(payload,{}))
    with pytest.raises(ValueError):cache.sql('a','b','c','q')


def test_range_requires_immutable_pin(tmp_path):
    with pytest.raises(ValueError,match='immutable'):
        ranges.Ranges('https://huggingface.co/datasets/a/b/resolve/main/file',tmp_path)


class Response:
    def __init__(self,status=206,content_range='bytes 0-0/20',body=b'x',etag='one'):
        self.status=status;self.headers={'Content-Range':content_range,'ETag':etag};self.body=body
    def __enter__(self):return self
    def __exit__(self,*a):pass
    def read(self,n):return self.body[:n]


URL='https://huggingface.co/datasets/a/b/resolve/'+'a'*40+'/file'


@pytest.mark.parametrize('response',[Response(status=200),Response(content_range='bytes 1-1/20'),Response(body=b'')])
def test_range_rejects_ignored_or_partial_response(tmp_path,monkeypatch,response):
    monkeypatch.setattr(ranges.urllib.request,'urlopen',lambda *a,**kw:response)
    with pytest.raises(ValueError): ranges.Ranges(URL,tmp_path)


def test_range_detects_source_mutation(tmp_path,monkeypatch):
    responses=iter([Response(),Response(content_range='bytes 1-1/20',etag='two')])
    monkeypatch.setattr(ranges.urllib.request,'urlopen',lambda *a,**kw:next(responses))
    reader=ranges.Ranges(URL,tmp_path)
    with pytest.raises(ValueError,match='mutation'):reader._range(1,1)


def test_range_detects_cache_metadata_tampering(tmp_path,monkeypatch):
    monkeypatch.setattr(ranges.urllib.request,'urlopen',lambda *a,**kw:Response())
    ranges.Ranges(URL,tmp_path)
    index=next(tmp_path.glob('*.json'));receipt=json.loads(index.read_text());receipt['end']=2
    index.write_text(json.dumps(receipt))
    with pytest.raises(ValueError,match='metadata'):ranges.Ranges(URL,tmp_path)

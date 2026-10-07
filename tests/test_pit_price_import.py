"""Real terminal OHLCV value, synthetic transport envelopes for hostile-input tests."""
import hashlib
import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from radar.lab.universe import LocalSecurityMaster
from radar.pit.builder import digest
from radar.pit.price_import import accept_prices

PIN='vt6qeesk27k07492k5jc5b7p04mf0s6o'


def inputs(tmp_path):
    raw=tmp_path/'raw';raw.mkdir()
    def cache(value):
        content=json.dumps(value,sort_keys=True).encode();sha=hashlib.sha256(content).hexdigest()
        (raw/(sha+'.raw')).write_bytes(content)
        return sha
    # Actual ATVI final exchange session, post-no-preference/stocks, CC BY-SA 4.0.
    rows=[{'date':'2023-10-12','act_symbol':'ATVI','open':'94.4800','high':'94.5400','low':'94.3100','close':'94.4200','volume':'7323451'}]
    sql=f"SELECT * FROM ohlcv AS OF '{PIN}' WHERE date='2023-10-12' AND act_symbol='ATVI'"
    sha=cache({'query_execution_status':'Success','sql_query':sql,'rows':rows})
    data={'rows':rows,'provider':'post-no-preference/stocks','license':'CC-BY-SA-4.0','source_version':PIN,
          'ancillary':{'split':[],'dividend':[],'symbol':[]},'queries':[{'sql':sql,'raw_sha256':sha}]}
    (raw/'ATVI.json').write_text(json.dumps(data))
    proof=raw/'adjustment.json';proof.write_text('synthetic test transport proof')
    license_sha=cache({'query_execution_status':'Success','sql_query':f"SELECT * FROM dolt_docs AS OF '{PIN}'",
        'rows':[{'doc_text':'Attribution-ShareAlike 4.0 International'}]})
    review={'source_version':PIN,'source_commit_time':'2026-10-06T05:30:37.288+00:00',
        'sessions':['2023-10-12'],'adjustment_evidence_file':proof.name,'adjustment_evidence_sha256':hashlib.sha256(proof.read_bytes()).hexdigest(),
        'license_raw_sha256':license_sha,'series':[{'file':'ATVI.json','payload_sha256':digest(data),'confidence':'verified','adjustment':'raw_no_splits',
        'valid_from':'2023-10-12','valid_to':'2023-10-12','source_symbol':'ATVI','security_id':'SEC-0000718877-COMMON'}]}
    csv=tmp_path/'security-master.csv'
    csv.write_text('security_id,symbol,valid_from,valid_to,listing_date,delisting_date,exchange,security_type,eligible,resolution_status\n'
        'SEC-0000718877-COMMON,ATVI,2021-09-01,2023-10-12,,,NASDAQ,common,true,verified\n')
    manifest=tmp_path/'security-master-manifest.json'
    manifest.write_text(json.dumps({'provider':'synthetic transport for real ATVI case','source_version':'test','coverage_start':'2021-09-01','coverage_end':'2023-10-12',
        'coverage_complete':False,'source_attested_completeness':False,'reconstruction_kind':'snapshot-interval-v1',
        'coverage_windows':[['2021-09-01','2023-10-12']],'output_sha256':hashlib.sha256(csv.read_bytes()).hexdigest()}))
    return raw,review,data,LocalSecurityMaster(csv,manifest)


def test_accepted_real_last_close_is_not_terminal_payout_and_never_overwrites(tmp_path):
    raw,review,data,m=inputs(tmp_path)
    output=tmp_path/'external.duckdb';r=accept_prices(raw,review,m,output)
    assert r['series'][0]['last_close']==94.42 and r['series'][0]['terminal_settlement'] is None
    with duckdb.connect(str(output),read_only=True) as c:
        assert c.execute('SELECT security_id,close FROM daily_bars').fetchone()==('SEC-0000718877-COMMON',94.42)
    with pytest.raises(ValueError,match='already exists'):accept_prices(raw,review,m,output)


@pytest.mark.parametrize('issue',['wrong_id','outside_scope','missing_session','raw_mutation','aggregate_mutation','split','unknown_basis','license'])
def test_external_prices_cannot_cross_identity_or_forge_basis(tmp_path,issue):
    raw,review,data,m=inputs(tmp_path)
    if issue=='wrong_id':review['series'][0]['security_id']='SEC-0001130713-COMMON'
    elif issue=='outside_scope':review['series'][0]['valid_to']='2023-10-11'
    elif issue=='missing_session':
        review['sessions'].insert(0,'2023-10-11')
        review['series'][0]['valid_from']='2023-10-11'
    elif issue=='raw_mutation':(raw/(data['queries'][0]['raw_sha256']+'.raw')).write_text('mutated')
    elif issue=='aggregate_mutation':data['rows'][0]['close']='95.0000'
    elif issue=='split':data['ancillary']['split']=[{'ex_date':'2023-10-12'}]
    elif issue=='unknown_basis':review['series'][0]['adjustment']='unknown'
    elif issue=='license':data['license']='unspecified'
    (raw/'ATVI.json').write_text(json.dumps(data));review['series'][0]['payload_sha256']=digest(data)
    with pytest.raises(ValueError):accept_prices(raw,review,m,tmp_path/'external.duckdb')


def test_sql_row_limit_is_not_a_successful_capture(tmp_path,monkeypatch):
    import radar.pit.public_prices as p
    raw={'query_execution_status':'RowLimit','sql_query':'SELECT 1','rows':[]}
    content=json.dumps(raw).encode();sha=hashlib.sha256(content).hexdigest();(tmp_path/(sha+'.raw')).write_bytes(content)
    monkeypatch.setattr(p,'capture',lambda *_args,**_kwargs:{'raw_sha256':sha})
    with pytest.raises(ValueError,match='failed/truncated'):p.query('SELECT 1',tmp_path)

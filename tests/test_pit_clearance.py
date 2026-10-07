"""Clearance regressions use synthetic evidence envelopes, never formal PASS claims."""
from copy import deepcopy
import json

import pandas as pd
import pytest

from radar.pit.actions import validate_no_material_action
from radar.pit.builder import digest
from radar.pit.price_import import merge_price_gaps
from radar.pit.public_prices import acquire_sessions
from radar.pit.resolution import ResolutionQueue, resolve_task
from radar.pit.run import MEMBERSHIP_CHECKS, freeze_file, readiness, scoped_membership_attested
from radar.pit.trust import enrich, load_catalog
from test_pit_price_import import inputs as price_inputs
from test_pit_run import inputs, rehash, ROOT


def no_action():
    types=['split','reverse_split','symbol_change','merger','cash_acquisition','delisting',
           'exchange_transfer','dividend','bankruptcy','equity_cancellation']
    return {'security_id':'ID','review_start':'2024-01-01','review_end':'2025-01-01',
        'result':'reviewed_no_material_action','event_types_checked':types,'reviewer_logic_version':'fixture-v1',
        'sources_checked':[{'url':'https://example.org/synthetic','source_version':'fixture',
            'raw_sha256':'a'*64,'identity_bound':True,'coverage_complete':True,
            'start':'2024-01-01','end':'2025-01-01','event_types_checked':types}]}


def test_no_material_action_requires_positive_source_coverage():
    r=no_action();d=['2024-06-03'];hashes={'a'*64}
    assert validate_no_material_action(r,'ID',d,[],hashes)
    r['sources_checked']=[]
    assert not validate_no_material_action(r,'ID',d,[],hashes)


@pytest.mark.parametrize('change',['hash','scope','split_only','known_event','identity'])
def test_action_source_mutation_and_incomplete_negative_evidence(change):
    r=no_action();actions=[]
    if change=='hash':r['sources_checked'][0]['raw_sha256']='b'*64
    if change=='scope':r['sources_checked'][0]['end']='2024-01-02'
    if change=='split_only':r['sources_checked'][0]['event_types_checked']=['split']
    if change=='identity':r['sources_checked'][0]['identity_bound']=False
    if change=='known_event':actions=[{'security_id':'ID','event_type':'dividend','effective_date':'2024-06-03'}]
    assert not validate_no_material_action(r,'ID',['2024-06-03'],actions,{'a'*64})


def gap_inputs(tmp_path):
    _,_,_,master=price_inputs(tmp_path)
    columns={'security_id':'SEC-0000718877-COMMON','symbol':'ATVI','open':94.48,'high':94.54,
        'low':94.31,'close':94.42,'volume':7323451,'adjustment':'raw'}
    base=pd.DataFrame([{**columns,'date':'2023-10-11'}]);incoming=pd.DataFrame([{**columns,'date':'2023-10-12'}])
    review={'security_id':columns['security_id'],'verified':True,'identity_bound':True,'price_basis':'raw',
        'source_version':'synthetic','license':'synthetic test only','source_hashes':['a'*64],
        'incoming_rows_sha256':digest(json.loads(incoming.to_json(orient='records')))}
    return base,incoming,master,review


def test_accepted_exact_session_gap_fill(tmp_path):
    base,incoming,master,review=gap_inputs(tmp_path)
    merged=merge_price_gaps(base,incoming,['2023-10-11','2023-10-12'],master,review,{'a'*64})
    assert list(merged.date)==['2023-10-11','2023-10-12']
    assert list(base.date)==['2023-10-11']


@pytest.mark.parametrize('change',['adjusted','overlap','conflict','partial','identity','source_mutation'])
def test_partial_session_merge_rejects_conflicts_and_bad_basis(tmp_path,change):
    base,incoming,master,review=gap_inputs(tmp_path)
    if change=='adjusted':base['adjustment']='split'
    if change in {'overlap','conflict'}:
        incoming['date']='2023-10-11'
        if change=='conflict':incoming['close']=94.5
    if change=='partial':incoming=incoming.iloc[:0]
    if change=='identity':incoming['security_id']='ANOTHER-ISSUER'
    if change=='source_mutation':incoming['volume']=1
    with pytest.raises(ValueError):merge_price_gaps(base,incoming,['2023-10-11','2023-10-12'],master,review,{'a'*64})


def test_gap_acquisition_never_requests_present_sessions(tmp_path,monkeypatch):
    import radar.pit.public_prices as module
    calls=[]
    def query(sql,cache):
        calls.append(sql);return [],{'url':'https://example.org','raw_sha256':'a'*64,'sql':sql}
    monkeypatch.setattr(module,'query',query)
    assert acquire_sessions('ATVI','vt6qeesk27k07492k5jc5b7p04mf0s6o',[],tmp_path)['rows']==0
    assert calls==[]
    acquire_sessions('ATVI','vt6qeesk27k07492k5jc5b7p04mf0s6o',['2023-10-12'],tmp_path)
    assert len(calls)==4 and "date IN ('2023-10-12')" in calls[0]
    assert '2023-10-11' not in ''.join(calls)


def test_resolution_worker_skips_complete_prices(tmp_path,monkeypatch):
    m,*_=inputs(tmp_path)
    row=m['dependencies'][0]
    def forbidden(*args,**kwargs):raise AssertionError('complete prices must not be downloaded')
    monkeypatch.setattr('radar.pit.public_prices.acquire_sessions',forbidden)
    catalog={'mappings':[{'security_id':'ID-A','confidence':'verified','source':'fixture'}]}
    out=resolve_task(tmp_path,{'payload':{'dependency':row}},network=True,pin='unused',catalog=catalog)
    assert out['status']=='blocked' and out['artifacts']==[]
    assert any('price scope complete' in r for r in out['reasons'])


def test_membership_policy_requires_all_seven_bound_checks(tmp_path):
    m,*_=inputs(tmp_path);m['source_attested_membership']=False
    sha=next(iter(m['files'].values()))['sha256']
    checks={k:{'status':'verified','explanation':'synthetic scope test','evidence_hashes':[sha]} for k in MEMBERSHIP_CHECKS}
    m['population_attestation']={'policy':'pit-formal-membership-v1','verified':True,
        'start':m['window'][0],'end':m['window'][2],'population_sha256':digest(m['population']),
        'source_hashes':[sha],'reviewer_logic_version':'fixture','checks':checks,
        'sources':[{'url':'https://example.org/fixture','source_version':'fixture','raw_sha256':sha,
                    'official_complete_population':True}]}
    assert scoped_membership_attested(m,{sha})
    del checks['classification_boundary']
    assert not scoped_membership_attested(m,{sha})
    assert readiness(rehash(m))['scorecard']['Membership']=='FAIL'


def test_formal_price_gate_has_no_99_9_percent_exception(tmp_path):
    m,*_=inputs(tmp_path);m['dependencies'][0]['missing_sessions']=[m['sessions'][0]]
    r=readiness(rehash(m))
    assert r['scorecard']['Price']=='FAIL' and not r['preflight_ready']
    assert r['scorecard']['LEAN Native Execution']=='NOT_RUN'


def test_real_iren_root_collision_resolves_only_with_official_identity():
    catalog=load_catalog(ROOT/'config/pit_trust_evidence.json')
    base={'symbol':'IREN','exchange':'NASDAQ','security_type':'common','eligible':True,
        'listing_date':'','delisting_date':'','resolution_status':'unresolved'}
    rows=pd.DataFrame([{**base,'security_id':'OBS-449bb6f3aa23209884239c73','valid_from':'2021-11-18',
        'valid_to':'2024-12-06','security_name':'Iris Energy Limited Ordinary Shares'},
        {**base,'security_id':'OBS-626ad46887c682e17d3cf605','valid_from':'2024-12-07',
        'valid_to':'2026-10-07','security_name':'IREN Limited Ordinary Shares'}])
    out,_=enrich(rows,catalog)
    assert set(out.security_id)=={'SEC-0001878848-ORDINARY'}
    assert out.resolution_status.eq('verified').all()
    candidate=deepcopy(catalog)
    for r in candidate['mappings']:
        if r['symbol']=='IREN':r['confidence']='inferred'
    unverified,_=enrich(rows,candidate)
    assert unverified.security_id.nunique()==2


def test_bulk_identity_conflicting_sources_never_certify(tmp_path):
    c=load_catalog(ROOT/'config/pit_trust_evidence.json')
    iren=next(m for m in c['mappings'] if m['symbol']=='IREN')
    c['mappings'].append({**iren,'security_id':'DIFFERENT-ISSUER','issuer_id':'CIK-OTHER'})
    path=tmp_path/'conflict.json';path.write_text(json.dumps(c))
    with pytest.raises(ValueError,match='overlapping verified symbol'):load_catalog(path)


def test_queue_iteration_retains_old_attempt_and_new_dependency(tmp_path):
    m,*_=inputs(tmp_path);q=ResolutionQueue(tmp_path/'queue.sqlite3');q.seed(m)
    task=q.claim();q.finish(task,{'status':'blocked','reason':'fixture missing source'})
    m['dependencies'][0]['certificate']['source_version']='new-evidence';rehash(m);q.seed(m)
    new=q.claim()
    assert new['payload']['dependency_sha256']==m['dependency_sha256'] and new['task_id']!=task['task_id']
    with q.connect() as c:assert c.execute('SELECT COUNT(*) FROM task_attempt_event').fetchone()[0]==1

"""Policy regressions: relaxed paperwork never relaxes causal/identity economics."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import os
from uuid import uuid4

import pandas as pd
import pytest

from radar.pit.builder import digest
from radar.pit.execution import execution_inputs
from radar.pit.research import (GATES, MEMBERSHIP_CHECKS, POLICY, classify_identity,
    core_membership, local_research_readiness, price_anomalies, research_readiness, sensitivity)
from radar.pit.run import readiness
from test_pit_run import inputs
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from download_pit_research_prices import parse_aggregate
from finalize_pit_research_evidence import dividend_bound

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def rules():
    return json.loads((ROOT/'config/pit_research_grade_rules.json').read_text())


def record(symbol='AAA', name='Alpha Incorporated Common Stock'):
    return {'security_id':'A','membership_sessions':['2025-01-06'], 'actions':[],
        'mappings':[{'symbol':symbol,'valid_from':'2020-01-01','valid_to':None,
                     'exchange':'NYSE','security_type':'common','eligible':True,'security_name':name}]}


def observed():
    return [{'cik':'1','name':'Alpha Inc','available_on':'2025-01-02'},
            {'cik':'1','name':'Alpha Inc','available_on':'2025-01-03'}]


def prices(days, sid='A'):
    return pd.DataFrame([{'date':d,'security_id':sid,'open':10.,'high':11.,'low':9.,'close':10.,'volume':3000000}
                         for d in days])


def profiles():
    return {p:{'candidate_ids':['day/A','day/B'],'contract_sha256':'same',
        'unknown_impact_bounded':True,'win_rate':.5,'path_success':.45,'mfe':.08,'mae':-.04,
        'native_return':.02,'native_drawdown':-.03,'average_trade':.004,'trade_count':20,
        'fee_equity_fraction':.001} for p in 'ABC'}


def fixture_audit(manifest, rules):
    files=list(manifest['files'].values()); hashes=[x['sha256'] for x in files]
    check={'status':'PASS','explanation':'synthetic test evidence only','evidence_hashes':hashes}
    audit={'policy':POLICY,'dependency_sha256':manifest['dependency_sha256'],'rules_sha256':digest(rules),
        'files':files,'gates':{g:deepcopy(check) for g in GATES},
        'membership':{'checks':{k:deepcopy(check) for k in MEMBERSHIP_CHECKS}},
        'scope':{'unresolved_identities':0,'missing_prices':0,'unhandled_material_actions':0,
                 'unhandled_terminals':0,'unbounded_unknown_members':0},
        'causal_verified':True,'hard_failures':[],'ordinary_dividend':{'portfolio_return_bound':0.},
        'sensitivity_profiles':profiles()}
    audit['audit_sha256']=digest(audit)
    return audit


def test_low_risk_identity_auto_pass(rules):
    assert classify_identity(record(),observed(),rules)['research_identity_pass']


@pytest.mark.parametrize('symbol',['BBBY','BYON','OSTK','FB','META'])
def test_high_reuse_remains_blocked(rules,symbol):
    result=classify_identity(record(symbol),observed(),rules)
    assert result['level']=='C' and not result['research_identity_pass']


def test_multiple_cik_class_ambiguity_blocked(rules):
    assert classify_identity(record(),observed()+[{'cik':'2','name':'Alpha Inc','available_on':'2025-01-03'}],rules)['level']=='C'
    assert classify_identity(record(name='Alpha Class A Common Stock'),observed(),rules)['level']=='C'


def test_future_issuer_evidence_cannot_select_past(rules):
    assert classify_identity(record(),observed(),rules,as_of='2025-01-01')['level']=='B'
    assert classify_identity(record(),observed(),rules,as_of='2025-01-06')['level']=='A'


def test_future_terminal_does_not_retroactively_remove_member(rules):
    r=record();r['actions']=[{'event_type':'bankruptcy','effective_date':'2025-06-01'}]
    assert classify_identity(r,observed(),rules,as_of='2025-01-06')['level']=='A'
    assert classify_identity(r,observed(),rules,as_of='2025-06-01')['level']=='C'


def test_split_anomaly_escalation(rules):
    frame=prices(['2025-01-02','2025-01-03']);frame.loc[1,['open','close','low','high']]=[1.,1.,.9,1.1]
    assert price_anomalies(frame,rules)[0]['kind']=='split_like_jump'


def test_missing_price_is_unknown_competitor(rules):
    days=pd.bdate_range('2024-01-01',periods=127).strftime('%Y-%m-%d').tolist()
    result=core_membership(days[-1],[{'security_id':'A','security_type':'common'},
        {'security_id':'FAILED','security_type':'common'}],prices(days[:-1]),days,rules)
    assert result['security_ids']==['A'] and result['unknown_security_ids']==['FAILED']
    assert not result['definitive'] and result['possible_rank_displacement']==1


def test_known_rule_failure_can_be_proven_despite_missing_history(rules):
    days=pd.bdate_range('2024-01-01',periods=127).strftime('%Y-%m-%d').tolist()
    bars=prices(days[-5:-1]);bars['volume']=100
    result=core_membership(days[-1],[{'security_id':'A','security_type':'common'}],bars,days,rules)
    assert result['rejected']['A']=='known_insufficient_daily_liquidity'
    assert result['unknown_security_ids']==[]


def test_core_is_causal_dynamic_not_today_survivors(rules):
    days=pd.bdate_range('2024-01-01',periods=127).strftime('%Y-%m-%d').tolist()
    members=[{'security_id':'A','security_type':'common'}];bars=prices(days[:-1])
    before=core_membership(days[-1],members,bars,days,rules)
    future=prices(['2026-01-01']);future['volume']=0;future['close']=.01
    after=core_membership(days[-1],members,pd.concat([bars,future]),days+['2026-01-01'],rules)
    assert before==after and before['causal_cutoff']==days[-2]


def test_future_ipo_exclusion_and_later_delisted_inclusion(rules):
    days=pd.bdate_range('2024-01-01',periods=127).strftime('%Y-%m-%d').tolist()
    members=[{'security_id':'A','security_type':'common','delisting_date':'2025-01-01'},
             {'security_id':'IPO','security_type':'common','listing_date':'2025-01-01'}]
    result=core_membership(days[-1],members,prices(days[:-1]),days,rules)
    assert result['security_ids']==['A'] and result['rejected']['IPO']=='future_listing'


def test_historical_core_reconstructs_same_day(rules):
    days=pd.bdate_range('2024-01-01',periods=127).strftime('%Y-%m-%d').tolist()
    members=[{'security_id':'A','security_type':'common'}];bars=prices(days[:-1])
    assert core_membership(days[-1],members,bars,days,rules)==core_membership(days[-1],members,bars.sample(frac=1),days,rules)


def test_sensitivity_includes_all_metrics_and_hidden_missing_population(rules):
    p=profiles();assert sensitivity(p,rules)['status']=='PASS'
    p['C']['native_return']=.5;assert sensitivity(p,rules)['status']=='FAIL'
    p=profiles();p['A']['unknown_impact_bounded']=False
    assert 'unbounded' in sensitivity(p,rules)['failures'][0]
    p=profiles();p['B']['trade_count']=None;assert sensitivity(p,rules)['status']=='FAIL'


def test_preflight_sensitivity_does_not_require_future_native_results(rules):
    p=profiles()
    for x in p.values(): x['native_return']=None;x['trade_count']=None
    assert sensitivity(p,rules,stage='scanner')['status']=='PASS'
    assert sensitivity(p,rules)['status']=='FAIL'


def test_strict_research_gate_separation(tmp_path,rules):
    manifest=inputs(tmp_path)[0]
    manifest['source_attested_membership']=False
    manifest['dependency_sha256']=digest({k:v for k,v in manifest.items() if k!='dependency_sha256'})
    audit=fixture_audit(manifest,rules)
    assert not readiness(manifest)['preflight_ready']
    result=research_readiness(manifest,audit,rules)
    assert result['preflight_ready'] and result['quality_tier']=='research-grade' and not result['formal_pit_ready']
    _,_,dataset=execution_inputs(manifest,quality_tier='research-grade',research_audit=audit,research_rules=rules)
    assert dataset['label']=='Research-Grade PIT'


def test_missing_adjusted_or_terminal_cannot_be_declared_pass(tmp_path,rules):
    manifest=inputs(tmp_path)[0]
    manifest['dependencies'][0]['missing_sessions']=['2025-01-06']
    manifest['dependencies'][0]['price_sources'][0]['adjustment']='split'
    manifest['dependency_sha256']=digest({k:v for k,v in manifest.items() if k!='dependency_sha256'})
    audit=fixture_audit(manifest,rules)
    result=research_readiness(manifest,audit,rules)
    assert not result['preflight_ready'] and result['scorecard']['Research price']=='FAIL'


def test_ordinary_dividend_bounded_disclosure_does_not_waive_split(tmp_path,rules):
    manifest=inputs(tmp_path)[0]
    row=manifest['dependencies'][0];sha=row['mappings'][0]['identity_evidence_hash']
    row['actions']=[{'event_id':'cash-ordinary','event_type':'dividend','effective_date':'2025-01-08',
        'confidence':'verified','handling_mode':'blocked','source':{'raw_sha256':sha},
        'review':{'ordinary_cash_dividend':True}}]
    manifest['dependency_sha256']=digest({k:v for k,v in manifest.items() if k!='dependency_sha256'})
    audit=fixture_audit(manifest,rules)
    audit['ordinary_dividend'].update(portfolio_return_bound=.0001,ordinary_event_ids=['cash-ordinary'])
    audit['audit_sha256']=digest({k:v for k,v in audit.items() if k!='audit_sha256'})
    assert research_readiness(manifest,audit,rules)['preflight_ready']
    _,_,dataset=execution_inputs(manifest,quality_tier='research-grade',research_audit=audit,research_rules=rules)
    assert not dataset['securities']['AAA']['actions']
    assert dataset['ordinary_dividend_limitation']['portfolio_return_bound']==.0001
    row['actions'][0].update(event_type='split',ratio=10.,handling_mode='native_raw_split')
    manifest['dependency_sha256']=digest({k:v for k,v in manifest.items() if k!='dependency_sha256'})
    audit['dependency_sha256']=manifest['dependency_sha256']
    audit['audit_sha256']=digest({k:v for k,v in audit.items() if k!='audit_sha256'})
    assert not research_readiness(manifest,audit,rules)['preflight_ready']


def test_api_label_missing_artifact_no_fallback(tmp_path):
    report=local_research_readiness(tmp_path)
    assert report['label']=='Research-Grade PIT' and report['fallback']=='forbidden'
    assert not report['preflight_ready']
    js=(ROOT/'site/dist/lab.js').read_text(encoding='utf-8')
    api=(ROOT/'src/radar/local_api.py').read_text(encoding='utf-8')
    assert '/api/lab/pit-research-readiness' in js and '/api/lab/pit-research-readiness' in api
    assert 'Research-Grade PIT Readiness' in js


def test_no_silent_execution_fallback(tmp_path):
    manifest=inputs(tmp_path)[0]
    with pytest.raises(ValueError,match='no fallback'): execution_inputs(manifest,quality_tier='research-grade')
    with pytest.raises(ValueError,match='unknown'): execution_inputs(manifest,quality_tier='current_snapshot')


def test_daily_aggregate_count_prevents_truncation():
    with pytest.raises(ValueError,match='truncated'):
        parse_aggregate([{'date':'2025-01-02','n':2,'bars':[['AAA',1,1,1,1,10]]}],'2025-01-02',None)


def test_dividend_ex_date_entry_not_entitled_and_exposure_not_portfolio_return():
    days=['2025-01-02','2025-01-03','2025-01-06']
    signals=[{'security_id':'A','signal_date':days[0]}]
    source=[{'security_id':'A','date':days[1],'open':10.}]
    cash=[{'security_id':'A','date':d,'amount':.1} for d in days[1:]]
    result=dividend_bound(signals,days,source,cash,1/3)
    assert result['possible_events']==1 and result['known_exposure_sum']==pytest.approx(.01/3)
    assert result['portfolio_return_upper_bound'] is None


def test_frozen_research_acceptance_cannot_use_newer_default(tmp_path):
    from radar.pit.research import load_research_acceptance
    from radar.pit.run import freeze_file
    audit=tmp_path/'audit.json';policy=tmp_path/'rules.json'
    audit.write_text('{}');policy.write_text('{}')
    refs=[freeze_file(audit),freeze_file(policy)]
    assert load_research_acceptance(*refs)==({}, {})
    policy.write_text('{"changed":true}')
    with pytest.raises(ValueError,match='changed'): load_research_acceptance(*refs)


def test_live_api_research_label_and_absent_artifact(monkeypatch,tmp_path):
    from radar import local_api
    from http.server import ThreadingHTTPServer
    from threading import Thread
    from urllib.request import Request,urlopen
    monkeypatch.setattr(local_api,'ROOT',tmp_path)
    server=ThreadingHTTPServer(('127.0.0.1',0),local_api.make_handler({'http://127.0.0.1:4174'}))
    thread=Thread(target=server.serve_forever,daemon=True);thread.start()
    try:
        with urlopen(Request(f'http://127.0.0.1:{server.server_port}/api/lab/pit-research-readiness',
                             headers={'Origin':'http://127.0.0.1:4174'}),timeout=3) as response:
            body=json.load(response)
            assert response.status==200 and body['label']=='Research-Grade PIT'
            assert body['fallback']=='forbidden' and not body['research_pit_ready']
    finally:
        server.shutdown();server.server_close();thread.join(timeout=2)


@pytest.mark.skipif(os.environ.get('STOCK_RADAR_TEST_LEAN')!='1',reason='explicit native LEAN opt-in')
def test_native_research_grade_reconciliation_and_label(tmp_path,rules):
    from radar.backtest.costs import load_fee_config
    from radar.lean.export import prepare_bundle
    from radar.lean.runtime import installation,invoke
    from radar.lean.result_adapter import normalize
    manifest,metadata,execution,_=inputs(tmp_path)
    manifest['source_attested_membership']=False
    manifest['dependency_sha256']=digest({k:v for k,v in manifest.items() if k!='dependency_sha256'})
    audit=fixture_audit(manifest,rules)
    metadata.update(quality_tier='research-grade',run_pit_readiness=research_readiness(manifest,audit,rules))
    signals,prices,dataset=execution_inputs(manifest,quality_tier='research-grade',research_audit=audit,research_rules=rules)
    home,identity=installation(ROOT);output=tmp_path/'native-research'
    path=prepare_bundle(home,output,metadata,pd.to_datetime(manifest['sessions']).tolist(),signals,prices,
                        execution,load_fee_config(ROOT/'config/research.yaml'),pit_dataset=dataset)
    raw=invoke(ROOT,output,path,str(uuid4()),lambda _:None,lambda:False,identity)
    result,metrics=normalize(output,raw,identity)
    assert metrics['trade_count']==1 and result['pit_execution_dataset']['quality_tier']=='research-grade'
    assert result['run_metadata']['run_pit_readiness']['label']=='Research-Grade PIT'
    assert result['run_metadata']['run_pit_readiness']['scorecard']['Result Reconciliation']=='PASS'

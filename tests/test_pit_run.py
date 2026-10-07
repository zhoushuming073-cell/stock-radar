"""Full-population closure, byte locks, fail-safe and opt-in native PIT parity."""
from copy import deepcopy
from dataclasses import replace
import json
import os
from pathlib import Path
from uuid import uuid4

import duckdb
import pandas as pd
import pytest

from radar.backtest.costs import load_fee_config
from radar.lab.parameters import execution_defaults_from_legacy
from radar.lab.universe import LocalSecurityMaster
from radar.lean.export import prepare_bundle
from radar.lean.runtime import installation, invoke, verify_bundle, digest as file_digest
from radar.lean.result_adapter import normalize
from radar.pit.actions import corporate_actions, factor_lines, split_adjust
from radar.pit.builder import digest
from radar.pit.execution import execution_inputs
from radar.pit.resolution import ResolutionQueue
from radar.pit.run import build_dependency, freeze_file, readiness, require_ready, save_dependency, load_dependency

ROOT = Path(__file__).resolve().parents[1]


def inputs(tmp_path, *, action=None, second=False, benchmark_bad=None):
    days = ['2025-01-06', '2025-01-07', '2025-01-08', '2025-01-10', '2025-01-13', '2025-01-14']
    raw = tmp_path / 'evidence.raw'
    raw.write_text('synthetic fixture evidence, not a real source certification')
    sha = file_digest(raw)
    common = {'security_id':'ID-A', 'symbol':'AAA', 'valid_from':days[0], 'valid_to':days[-1],
              'listing_date':days[0], 'delisting_date':'', 'exchange':'NYSE', 'security_type':'common',
              'eligible':True, 'resolution_status':'verified', 'classification_confidence':'verified',
              'issuer_id':'CIK-1', 'share_class':'COMMON', 'identity_evidence_hash':sha}
    mappings = [common]
    if second:
        mappings.append({**common, 'security_id':'ID-NO-PRICE','symbol':'BBB','resolution_status':'unresolved',
                         **({'valid_from':'2025-01-15','valid_to':'2026-01-15','listing_date':'2025-01-15'} if second=='cold' else {})})
    catalog = {'sources':{'fixture':{'url':'https://example.org/fixture','source_version':'fixture1','raw_sha256':sha}}, 'events':[]}
    reviews = {}
    if action == 'rename':
        mappings = [{**common,'valid_to':days[1]}, {**common,'symbol':'NEW','valid_from':days[2]}]
        catalog['events'] = [{'security_id':'ID-A','event_type':'symbol_change','effective_date':days[2],
                              'old_symbol':'AAA','new_symbol':'NEW','confidence':'verified','source':'fixture'}]
    if action in {'split','reverse_split'}:
        ratio = 2 if action == 'split' else .5
        catalog['events'] = [{'security_id':'ID-A','event_type':action,'effective_date':days[2],
                              'to_factor':ratio,'for_factor':1,'confidence':'verified','source':'fixture'}]
        reviews[f'ID-A:{action}:{days[2]}'] = {'factor_verified':True}
    if action == 'cash':
        mappings = [{**common,'valid_to':days[2]}]
        catalog['events'] = [{'security_id':'ID-A','event_type':'cash_acquisition','effective_date':days[3],
                              'documented_cash_consideration':11,'confidence':'verified','source':'fixture'}]
        reviews[f'ID-A:cash_acquisition:{days[3]}'] = {'settlement_verified':True,
            'settlement_policy':'cash_entitlement_at_effective_date','settlement_date':days[3],
            'last_tradable_session':days[2],'currency':'USD','cash_per_share':11,'settlement_fee':0}
    csv = tmp_path / 'security-master.csv'
    pd.DataFrame(mappings).to_csv(csv,index=False)
    mp = tmp_path / 'security-master-manifest.json'
    mp.write_text(json.dumps({'provider':'synthetic_fixture','source_version':'fixture1',
        'coverage_start':days[0], 'coverage_end':days[-1], 'coverage_complete':True}))
    prices = []
    for i, day in enumerate(days):
        if action != 'cash' or i < 3:
            price = 10. if action not in {'split','reverse_split'} or i < 2 else 10. / ratio
            prices.append({'date':day,'symbol':'NEW' if action=='rename' and i>=2 else 'AAA',
                'security_id':'ID-A','open':price,'high':price,'low':price,'close':price,'volume':1000000,
                'provider':'fixture','feed':'fixture','adjustment':'raw'})
        for symbol in ('SPY','QQQ'):
            prices.append({'date':day,'symbol':symbol,'security_id':None,'open':100.,'high':100.,
                           'low':100.,'close':100.,'volume':1000000,'provider':'fixture','feed':'fixture','adjustment':'raw'})
    if benchmark_bad == 'invalid':
        next(p for p in prices if p['symbol']=='SPY')['close']=0
    if benchmark_bad == 'duplicate':
        prices.append(dict(next(p for p in prices if p['symbol']=='SPY')))
    database = tmp_path/'features.duckdb'
    with duckdb.connect(str(database)) as c:
        c.register('rows',pd.DataFrame(prices));c.execute('CREATE TABLE daily_bars AS SELECT * FROM rows')
    sidecar=tmp_path/'security-master-feature-store.json'
    sidecar.write_text(json.dumps({'database':str(database),'database_sha256':file_digest(database),
                                  'master_output_sha256':file_digest(csv)}))
    master = LocalSecurityMaster(csv,mp)
    frame=pd.DataFrame([{'date':pd.Timestamp(days[0]),'symbol':'AAA','security_id':'ID-A'}])
    execution = execution_defaults_from_legacy({'initial_capital':10000.,'max_new_candidates':1,
        'take_profit':None,'stop_loss':None,'max_holding_sessions':4,'entry_gap_min':-.1,'entry_gap_max':.1,
        'max_position_fraction':.4,'minimum_position_fraction':0.,'max_order_to_avg_dollar_volume':.1},
        slippage_bps=0.,execution_timing='next_open')
    metadata={'window':[days[0],days[0],days[-1]],'strategy_id':'fixture','strategy_version':'1.0',
              'config_hash':'config-frozen','resolved_config_hash':digest(execution),
              'resolved_config':{'values':{'execution':execution}}, 'universe_mode':'point_in_time'}
    signal={'signal_date':days[0],'symbol':'AAA','rank':1,'strategy_score':1.,'strategy_id':'fixture',
            'strategy_version':'1.0','reference_close':10.,'avg_dollar_volume_20':10000000.,'allocation_weight':1.}
    cert={'verified':True,'identity_bound':True,'price_basis':'raw','feature_basis':'causal_split_only',
          'source_version':'fixture1','license':'fixture-test-only','source_hashes':[sha],
          'start':days[0],'end':days[-1],'action_coverage_verified':True}
    certificates={'securities':{'ID-A':cert},'benchmarks':{'SPY':cert,'QQQ':cert},'actions':reviews}
    files={str(p):freeze_file(p) for p in (raw,csv,mp,sidecar,database)}
    manifest=build_dependency(master,database,pd.to_datetime(days),frame,[signal],metadata,
        catalog=catalog,certificates=certificates,files=files,warmup_sessions=1)
    return manifest, metadata, execution, prices


def rehash(manifest):
    manifest.pop('dependency_sha256',None)
    manifest['dependency_sha256']=digest(manifest)
    return manifest


def test_complete_population_includes_unpriced_not_selected_security(tmp_path):
    manifest,*_=inputs(tmp_path,second=True)
    assert {r['security_id'] for r in manifest['dependencies']}=={'ID-A','ID-NO-PRICE'}
    report=readiness(manifest)
    assert report['missing_prices'] == 1
    assert report['scorecard']['Identity']=='FAIL'
    with pytest.raises(ValueError,match='BLOCKED'):
        require_ready(manifest)


def test_unrelated_global_intervals_do_not_block_run(tmp_path):
    manifest,*_=inputs(tmp_path,second='cold')
    assert require_ready(manifest)['preflight_ready']
    assert len(manifest['dependencies'])==1
    assert manifest['population'][0]['feature_evaluation_ids']==['ID-A']


@pytest.mark.parametrize('field', ['source_hashes','license','price_basis','identity_bound','action_coverage_verified'])
def test_each_source_claim_is_required_not_a_single_ready_flag(tmp_path,field):
    manifest,*_=inputs(tmp_path)
    manifest['dependencies'][0]['certificate'].pop(field)
    with pytest.raises(ValueError,match='BLOCKED'):
        require_ready(rehash(manifest))


@pytest.mark.parametrize('change',['no_price','partial','adjusted','identity','class','membership','action','terminal'])
def test_critical_dependency_fail_safe(tmp_path,change):
    manifest,*_=inputs(tmp_path,action='cash' if change=='terminal' else None)
    row=manifest['dependencies'][0]
    if change in {'no_price','partial'}:row['missing_sessions']=[row['required_sessions'][0]]
    if change=='adjusted':row['price_sources'][0]['adjustment']='all'
    if change=='identity':row['mappings'][0]['resolution_status']='unresolved'
    if change=='class':row['mappings'][0]['security_type']='adr'
    if change=='membership':manifest['source_attested_membership']=False
    if change=='action':row['certificate']['action_coverage_verified']=False
    if change=='terminal':row['actions'][0]['handling_mode']='blocked'
    with pytest.raises(ValueError,match='BLOCKED'):require_ready(rehash(manifest))


def test_queued_manifest_and_physical_database_mutation(tmp_path):
    manifest,*_=inputs(tmp_path)
    ref=save_dependency(tmp_path,manifest)
    assert load_dependency(ref)==manifest
    db=tmp_path/'features.duckdb'
    with duckdb.connect(str(db)) as c:c.execute("UPDATE daily_bars SET close=9 WHERE symbol='AAA'")
    with pytest.raises(ValueError,match='source changed'):load_dependency(ref)


def test_dependency_hash_and_license_file_mutation(tmp_path):
    manifest,*_=inputs(tmp_path)
    altered=deepcopy(manifest);altered['signals'][0]['strategy_score']=99
    with pytest.raises(ValueError,match='dependency hash'):require_ready(altered)
    (tmp_path/'evidence.raw').write_text('license changed')
    with pytest.raises(ValueError,match='source changed'):require_ready(manifest)


@pytest.mark.parametrize('kind,ratio',[('split',2),('reverse_split',.5)])
def test_split_pipeline_does_not_double_adjust(tmp_path,kind,ratio):
    manifest,_,_,prices=inputs(tmp_path,action=kind)
    actions=manifest['dependencies'][0]['actions']
    raw=pd.DataFrame(prices);raw=raw.loc[raw.security_id.eq('ID-A')]
    before=split_adjust(raw,actions,'2025-01-07')
    after=split_adjust(raw,actions,'2025-01-08')
    assert before.iloc[0].close==10
    assert after.close.nunique()==1
    assert after.iloc[0].volume==1000000*ratio
    lines=factor_lines(actions,manifest['calendar'],{'2025-01-07':10})
    assert f'20250107,1,{1/ratio:g},10' in lines


def test_cash_policy_unknown_recovery_and_rename(tmp_path):
    manifest,*_=inputs(tmp_path,action='cash')
    assert require_ready(manifest)['scorecard']['Terminal']=='PASS'
    base={'security_id':'ID-A','effective_date':'2025-01-10','confidence':'verified','source':'fixture'}
    catalog={'sources':{'fixture':{'url':'https://example.org','raw_sha256':'x','source_version':'v'}},
             'events':[{**base,'event_type':k} for k in ('bankruptcy','delisting','merger','equity_cancellation')]}
    assert all(a['handling_mode']=='blocked' for a in corporate_actions(catalog))


def test_queue_is_resumable_idempotent_and_priority_safe(tmp_path):
    manifest,*_=inputs(tmp_path,second=True)
    queue=ResolutionQueue(tmp_path/'queue.sqlite3');queue.seed(manifest);queue.seed(manifest)
    assert sum(r['count'] for r in queue.summary())==2
    first=queue.claim();assert first['security_id']=='ID-NO-PRICE'
    queue.finish(first,{'status':'blocked','reason':'no official identity'})
    with pytest.raises(ValueError,match='lease lost'):queue.finish(first,{'status':'accepted'})


def test_causal_feature_split_boundary_and_future_mutation():
    from radar.pit.features import causal_identity_features
    from radar.features.elasticity import ElasticityConfig
    from radar.features.scoring import load_research_config
    days=pd.bdate_range('2023-01-03',periods=180)
    close=pd.Series([100.+i/10 for i in range(180)],index=days)
    raw=pd.DataFrame({'open':close,'high':close*1.01,'low':close*.99,'close':close,'volume':1e6},index=days)
    raw.index.name='date';raw.loc[days[140]:,['open','high','low','close']]/=10
    action={'security_id':'ID','event_type':'split','effective_date':str(days[140].date()),
            'handling_mode':'native_raw_split','confidence':'verified','ratio':10}
    cfg=load_research_config(ROOT/'config/research.yaml');ecfg=ElasticityConfig()
    result=causal_identity_features(raw,close,close,ecfg,cfg,actions=[action],security_id='ID')
    assert abs(result.loc[days[140],'ret_1'])<.01
    altered=raw.copy();altered.loc[days[150]:,'close']*=2
    future=causal_identity_features(altered,close,close,ecfg,cfg,actions=[{**action,'ratio':20}],security_id='ID')
    pd.testing.assert_frame_equal(result.loc[:days[139]],future.loc[:days[139]])


def test_unified_action_table_is_new_and_not_complete(tmp_path):
    from radar.pit.actions import write_action_store
    catalog={'sources':{'x':{'url':'https://example.org','source_version':'v','raw_sha256':'x'}},
             'events':[{'security_id':'ID','event_type':'bankruptcy','effective_date':'2023-01-01',
                        'source':'x','confidence':'verified'}]}
    path=tmp_path/'actions.duckdb';receipt=write_action_store(catalog,{},path)
    assert receipt['coverage_complete'] is False
    with duckdb.connect(str(path),read_only=True) as c:
        assert c.execute('SELECT handling_mode FROM corporate_action_event').fetchone()[0]=='blocked'
    with pytest.raises(ValueError,match='already exists'):write_action_store(catalog,{},path)


def test_reviewed_worker_acceptance_is_immutable_and_rechecks_raw(tmp_path):
    from test_pit_price_import import inputs as price_inputs
    from radar.pit.resolution import resolve_task
    import shutil
    raw,review,_,master=price_inputs(tmp_path)
    data=tmp_path/'data';data.mkdir()
    shutil.copy2(master.csv_path,data/master.csv_path.name)
    shutil.copy2(master.manifest_path,data/master.manifest_path.name)
    identity='SEC-0000718877-COMMON'
    decision={'dependency_sha256':'frozen','price_review':review,'raw_directory':str(raw)}
    folder=data/'pit/resolution-reviews';folder.mkdir(parents=True)
    (folder/(digest(identity)+'.json')).write_text(json.dumps(decision))
    task={'payload':{'dependency_sha256':'frozen','dependency':{'security_id':identity,'symbols':['ATVI'],
        'required_sessions':['2023-10-12'],'mappings':[{'resolution_status':'verified'}]}}}
    catalog={'mappings':[{'security_id':identity,'confidence':'verified','source':'official'}]}
    result=resolve_task(tmp_path,task,catalog=catalog)
    assert result['status']=='accepted' and result['installed_artifacts_modified'] is False
    assert resolve_task(tmp_path,task,catalog=catalog)['artifacts']==result['artifacts']
    (raw/(review['license_raw_sha256']+'.raw')).write_text('mutated license')
    with pytest.raises(ValueError,match='license hash'):resolve_task(tmp_path,task,catalog=catalog)


@pytest.mark.parametrize('action',[None,'rename','split','reverse_split','cash'])
def test_native_pit_pass_actions_and_reconciliation(tmp_path,action):
    if os.environ.get('STOCK_RADAR_TEST_LEAN')!='1':pytest.skip('Opt-in native LEAN test')
    manifest,metadata,execution,_=inputs(tmp_path,action=action)
    metadata['run_pit_readiness']=require_ready(manifest)
    signals,prices,dataset=execution_inputs(manifest)
    home,identity=installation(ROOT)
    output=tmp_path/'native'
    path=prepare_bundle(home,output,metadata,pd.to_datetime(manifest['sessions']).tolist(),signals,prices,
                        execution,load_fee_config(ROOT/'config/research.yaml'),pit_dataset=dataset)
    raw=invoke(ROOT,output,path,str(uuid4()),lambda _:None,lambda:False,identity)
    result,metrics=normalize(output,raw,identity)
    assert result['run_metadata']['run_pit_readiness']['scorecard']['Result Reconciliation']=='PASS'
    assert metrics['trade_count']==1
    if action in {'split','reverse_split','rename','cash'}:
        assert result['corporate_actions']
    if action=='cash':
        assert result['trades'][0]['exit_kind']=='corporate_action_settlement'
        assert result['trades'][0]['exit_execution']==11
    if action in {'split','reverse_split'}:
        trade=result['trades'][0]
        assert abs(trade['net_return'])<.01
    # Map/factor mutations must fail even if the price file is intact.
    mapping=next((output/'data/equity/usa/map_files').glob('*.csv'))
    original=mapping.read_text()
    mapping.write_text(original+'20511231,wrong\n')
    with pytest.raises(ValueError,match='data changed'):verify_bundle(output,file_digest(path))
    mapping.write_text(original)
    factor=next((output/'data/equity/usa/factor_files').glob('*.csv'))
    factor.write_text(factor.read_text()+'20511231,1,0.01,1\n')
    with pytest.raises(ValueError,match='data changed'):verify_bundle(output,file_digest(path))


@pytest.mark.parametrize('bad', ['invalid', 'duplicate'])
def test_benchmark_invalid_or_duplicate_session_blocks_run(tmp_path,bad):
    manifest,*_=inputs(tmp_path,benchmark_bad=bad)
    assert manifest['benchmarks'][0]['missing_sessions']==['2025-01-06']
    with pytest.raises(ValueError,match='BLOCKED'):require_ready(manifest)


@pytest.mark.parametrize('field',['start','end','source_version','identity_bound'])
def test_benchmark_certificate_covers_full_scope(tmp_path,field):
    manifest,*_=inputs(tmp_path)
    cert=deepcopy(manifest['benchmarks'][0]['certificate'])
    if field=='start':cert['start']='2025-01-07'
    elif field=='end':cert['end']='2025-01-13'
    else:cert.pop(field)
    manifest['benchmarks'][0]['certificate']=cert
    with pytest.raises(ValueError,match='BLOCKED'):require_ready(rehash(manifest))

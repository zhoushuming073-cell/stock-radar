from copy import deepcopy
import json
from pathlib import Path

from hypothesis import given, strategies as st
import numpy as np
import pandas as pd
import pytest

from radar.pit.shape import normalize_window
from radar.vision.quant_features import features_at, array_features, stratum
from radar.vision.quant_guided import load_quant_config, normalized_array, issuer_key, select
from radar.vision.quant_labels import HumanLabel, REASONS

CONFIG=Path(__file__).resolve().parents[1]/'config/quant_vision_labeling_v1.yaml'

def cfg(): return load_quant_config(CONFIG)

def window(n=126):
    c=np.r_[np.linspace(1,1.8,n-25),np.linspace(1.75,1.3,20),np.linspace(1.3,1.34,5)]
    return pd.DataFrame(dict(date=pd.bdate_range('2022-01-03',periods=n),open=c*.999,high=c*1.02,low=c*.98,close=c,volume=np.arange(n)+1.))

@given(st.floats(min_value=.001,max_value=1000,allow_nan=False,allow_infinity=False))
def test_future_mutation_and_constant_vendor_scale_cannot_change_past(k):
    f=window(); t=f.date.iloc[-1]; expected=features_at(f,t,cfg())
    future=f.iloc[-3:].copy(); future.date=pd.bdate_range(t+pd.Timedelta(days=1),periods=3)
    future[['open','high','low','close','volume']]*=k
    assert features_at(pd.concat([f,future],ignore_index=True),t,cfg())==expected
    scaled=f.copy(); scaled[['open','high','low','close']]*=k; scaled.volume*=k*2
    actual=features_at(scaled,t,cfg())
    for name in actual: assert actual[name]==pytest.approx(expected[name],rel=1e-8,abs=1e-8)

def test_bulk_normalization_matches_frozen_raw_and_future_split_is_ignored():
    f=window(60); raw=f.assign(basis='raw',source='fixture')
    actions=[{'date':f.date.iloc[30],'factor':2},{'date':f.date.iloc[-1]+pd.Timedelta(days=1),'factor':100}]
    expected=normalize_window(raw,f.date.iloc[-1],actions)
    actual=normalized_array(f[['open','high','low','close','volume']].to_numpy(),f.date,'raw',[(x['date'],x['factor']) for x in actions],f.date.iloc[-1])
    np.testing.assert_array_equal(actual,expected[['open','high','low','close','volume']].to_numpy())

@pytest.mark.parametrize('change',['future','duplicate','unknown_basis','invalid_split'])
def test_bulk_rejects_corrupt_windows(change):
    f=window(60); t=f.date.iloc[-1]; basis='split'; actions=[]
    if change=='future': t-=pd.Timedelta(days=1)
    if change=='duplicate': f.loc[1,'date']=f.loc[0,'date']
    if change=='unknown_basis': basis='unknown'
    if change=='invalid_split': basis='raw'; actions=[(f.date.iloc[30],-2)]
    with pytest.raises(ValueError): normalized_array(f[['open','high','low','close','volume']].to_numpy(),f.date,basis,actions,t)

@pytest.mark.parametrize('field,value',[('allowed_splits',['train','test']),('allowed_splits',['train','fresh']),
    ('output_dir','data/vision-research/pilot-v1'),('output_dir','../private'),('window_lengths',[60]),('repeat_fraction',1)])
def test_config_cannot_weaken_split_or_isolation(tmp_path,field,value):
    import yaml
    c=cfg(); c[field]=value; p=tmp_path/'bad.yaml'; p.write_text(yaml.safe_dump(c))
    with pytest.raises(ValueError): load_quant_config(p)

def test_identity_key_never_promotes_unknown_issuer_or_merges_by_ticker():
    assert issuer_key('OBS-abc')==('OBS-abc',False)
    assert issuer_key('SEC-0000000123-COMMON')==('CIK-0000000123',True)
    assert issuer_key('OBS-abc')!=issuer_key('OBS-def')

def test_extension_is_independent_of_good_shape_and_not_a_label():
    f=window(); a=features_at(f,f.date.iloc[-1],cfg())
    f.loc[len(f)-1,['open','high','low','close']]=[1.5,1.9,1.48,1.88]
    b=features_at(f,f.date.iloc[-1],cfg())
    assert b['extension_score']>a['extension_score']
    assert b['score_entry_location']<a['score_entry_location']
    assert not {'observe','entry','future_return'} & set(b)
    assert all(0<=v<=100 for k,v in b.items() if k.startswith('score_') or k.endswith('_score'))

def test_sampling_is_deterministic_diverse_and_one_issuer():
    c=cfg(); c['single_count']=25; c['sampling']['quotas']={k:5 for k in ['high','medium','boundary','conflict','control']}; c['anchors']=[]
    rows=[]
    for i in range(250):
        for length in [60,126]:
            rows.append(dict(security_id=f'OBS-{i}',issuer_key=f'OBS-{i}',issuer_known=False,decision_date=pd.Timestamp('2022-08-01'),
                length=length,year=2021+i%5,candidate_stratum=['high','medium','boundary','conflict','control'][i%5]))
    p=pd.DataFrame(rows); a,_=select(p,c); b,_=select(p,c)
    pd.testing.assert_frame_equal(a,b)
    assert len(a)==25 and not a.security_id.duplicated().any()
    assert set(a.sampling_layer)==set(c['sampling']['quotas'])
    assert a.conditional_path_probability.between(0,1,inclusive='right').all()
    assert (a['draw']!=a['selection_draw']).all()

def valid_label():
    return dict(task_id='single-a',annotation_id=1,ls_task_id=1,project_id=5,label_version='quant-human-v1',label_origin='smoke',
        observe='观察',entry='等回落或进一步确认',confidence='高',reasons=['最近涨得过多'],created_at='2026-10-09T00:00:00Z',
        updated_at='2026-10-09T00:00:00Z',repeat_group=None)

@pytest.mark.parametrize('field,value',[('observe','买入'),('entry','观察'),('label_version','human-vision-v1'),('label_origin','machine'),
    ('reasons',['真实资金流入']),('reasons',['前期强势','前期强势']),('created_at','2026-10-09')])
def test_human_contract_rejects_wrong_choice_version_or_namespace(field,value):
    row=valid_label(); row[field]=value
    with pytest.raises(ValueError): HumanLabel(**row)

def test_observe_and_wait_are_valid_independent_intentions():
    row=HumanLabel(**valid_label()); assert row.observe=='观察' and row.entry=='等回落或进一步确认'

@pytest.fixture
def label_bundle(tmp_path,monkeypatch):
    import radar.vision.quant_labels as mod
    monkeypatch.setattr(mod,'verify_quant',lambda b: {'status':'PASS'})
    (tmp_path/'label-studio-projects.json').write_text(json.dumps({'human':{'id':5},'smoke':{'id':6}}))
    (tmp_path/'bundle-receipt.json').write_text(json.dumps({'local_files_prefix':'/data/local-files/?d=quant'}))
    pd.DataFrame([{'task_id':'single-a','image_path':'images/a.png','repeat_group':None,'blind_id':'a','task_kind':'single'},
                  {'task_id':'single-b','image_path':'images/a.png','repeat_group':'a','blind_id':'a','task_kind':'single_repeat'}]).to_parquet(tmp_path/'sample-manifest.parquet')
    row={'id':1,'project':6,'data':{'task_id':'single-a','image':'/data/local-files/?d=quant/images/a.png'},
         'meta':{'label_version':'quant-human-v1','label_origin':'smoke'},'annotations':[
           {'id':7,'created_at':'2026-10-09T00:00:00Z','updated_at':'2026-10-09T00:00:00Z','result':[
             {'from_name':k,'to_name':'chart','type':'choices','value':{'choices':[v]}}
             for k,v in [('observe','观察'),('entry','等回落或进一步确认'),('confidence','高')]]}]}
    return tmp_path,row

@pytest.mark.parametrize('attack',['task_id','choice','version','project','origin','extra_identity','wrong_image','multiple_annotations','duplicate_task'])
def test_label_export_rejects_mapping_namespace_and_schema_attacks(label_bundle,attack):
    from radar.vision.quant_labels import parse_export
    b,row=label_bundle; row=deepcopy(row)
    if attack=='task_id': row['data']['task_id']='single-foreign'
    if attack=='choice': row['annotations'][0]['result'][0]['value']['choices']=['CURRENT BUY']
    if attack=='version': row['meta']['label_version']='old'
    if attack=='project': row['project']=5
    if attack=='origin': row['meta']['label_origin']='human'
    if attack=='extra_identity': row['data']['ticker']='AAPL'
    if attack=='wrong_image': row['data']['image']='foreign.png'
    if attack=='multiple_annotations': row['annotations'].append(deepcopy(row['annotations'][0]))
    payload=[row,row] if attack=='duplicate_task' else [row]
    with pytest.raises(ValueError): parse_export(b,payload,'smoke')

def test_label_import_idempotent_preserves_edits_and_rejects_conflicting_or_stale_revision(label_bundle):
    from radar.vision.quant_labels import import_labels
    b,row=label_bundle; p=b/'export.json'; p.write_text(json.dumps([row]))
    assert import_labels(b,p,'smoke')['new_revisions']==1
    assert import_labels(b,p,'smoke')['new_revisions']==0
    row['annotations'][0]['updated_at']='2026-10-09T01:00:00Z'
    row['annotations'][0]['result'][0]['value']['choices']=['不观察']; p.write_text(json.dumps([row]))
    assert import_labels(b,p,'smoke')['new_revisions']==1
    assert len(json.loads((b/'labels/smoke/revisions.json').read_text(encoding='utf-8')))==2
    snapshot=(b/'labels/smoke/labels.parquet').read_bytes()
    row['annotations'][0]['result'][0]['value']['choices']=['观察']; p.write_text(json.dumps([row]))
    with pytest.raises(ValueError,match='conflicting'): import_labels(b,p,'smoke')
    row['annotations'][0]['updated_at']='2026-10-08T23:00:00Z'; p.write_text(json.dumps([row]))
    with pytest.raises(ValueError,match='stale'): import_labels(b,p,'smoke')
    assert (b/'labels/smoke/labels.parquet').read_bytes()==snapshot
    assert not (b/'labels/human').exists()

def test_cancelled_skip_is_not_a_human_label(label_bundle):
    from radar.vision.quant_labels import parse_export
    b,row=label_bundle; row['annotations'][0]['was_cancelled']=True
    assert parse_export(b,[row],'smoke')==[]

@pytest.mark.parametrize('attack',['unknown','test','fresh','future_column','wrong_version','unsafe'])
def test_quant_contract_rejects_untrusted_population_and_future_columns(attack):
    from radar.vision.quant_contracts import validate_quant_frame
    c=cfg(); f=window(60)
    row=dict(security_id='OBS-a',decision_date=f.date.iloc[-1],length=60,split_assignment='train',
        membership_status='confirmed_member',shape_research_status='READY',issuer_key='OBS-a',issuer_known=False,
        candidate_stratum='high',year=2022,feature_version=c['feature_version'],**features_at(f,f.date.iloc[-1],c))
    good=pd.DataFrame([row]); validate_quant_frame(good,c)
    bad=good.copy()
    if attack=='unknown': bad['membership_status']='unknown'
    if attack in ('test','fresh'): bad['split_assignment']=attack
    if attack=='future_column': bad['future_return']=.5
    if attack=='wrong_version': bad['feature_version']='legacy'
    if attack=='unsafe': bad['shape_research_status']='QUARANTINED'
    with pytest.raises(ValueError): validate_quant_frame(bad,c)

def test_layout_migration_cannot_change_label_meaning():
    import importlib.util
    p=Path(__file__).resolve().parents[1]/'scripts/setup_quant_guided_label_studio.py'
    spec=importlib.util.spec_from_file_location('ls_setup',p); mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    xml=(p.parents[1]/'labeling/quant-guided-v1.xml').read_text(encoding='utf-8')
    assert mod.control_contract(xml)==mod.control_contract(xml.replace('min-width:500px','min-width:600px'))
    assert mod.control_contract(xml)!=mod.control_contract(xml.replace('当前可买','立即成交'))

def test_concurrent_import_lock_cannot_overwrite_labels(label_bundle):
    from radar.vision.quant_labels import import_labels
    b,row=label_bundle; p=b/'export.json'; p.write_text(json.dumps([row]))
    folder=b/'labels/smoke'; folder.mkdir(parents=True); (folder/'import.lock').write_text('other writer')
    with pytest.raises(ValueError,match='another import'): import_labels(b,p,'smoke')
    assert not (folder/'labels.parquet').exists()
    assert (folder/'import.lock').read_text()=='other writer'

"""Actual contracts and tamper rejection, using synthetic local-only windows."""
import json
from pathlib import Path
import shutil
from types import SimpleNamespace
from unittest.mock import patch
import duckdb
import numpy as np
import pandas as pd
import pytest
import yaml

from radar.pit.shape import canonical_hash,ShapeWindow
from radar.vision.labeling import build_label_studio_bundle,load_config,import_label_studio_export,_add_repeats
from radar.vision.render import render_blind_png
from radar.vision.verification import verify,file_hash
from PIL import Image
from io import BytesIO

@pytest.fixture(scope='module')
def synthetic_bundle(tmp_path_factory):
    root=tmp_path_factory.mktemp('vision-contract')
    core=root/'synthetic-core';core.mkdir();dbpath=core/'shape.duckdb'
    records=[]
    for i in range(12):
        records.append((f'SEC-{i}',pd.Timestamp('2024-01-05' if i<6 else '2025-01-06'),
                        60 if i%2 else 126,'train' if i<6 else 'validation','confirmed_member','READY',True))
    c=duckdb.connect(str(dbpath))
    c.execute('CREATE TABLE visual_window_index(security_id VARCHAR,decision_date DATE,length INT,split_assignment VARCHAR,membership_status VARCHAR,shape_research_status VARCHAR,supported_membership BOOLEAN)')
    c.executemany('INSERT INTO visual_window_index VALUES (?,?,?,?,?,?,?)',records);c.close()
    source_hash=file_hash(dbpath)
    class FakeAPI:
        fingerprint='a'*64
        def __enter__(self):
            self.core=SimpleNamespace(directory=core,manifest={'database_sha256':source_hash},connection=duckdb.connect(str(dbpath),read_only=True))
            return self
        def __exit__(self,*args):self.core.connection.close()
        def window(self,sid,decision,length):
            x=np.linspace(1,1.5,length)
            f=pd.DataFrame({'date':pd.bdate_range(end=decision,periods=length),'open':x,'high':x+.1,'low':x-.1,'close':x+.02,'volume':np.linspace(.1,1,length)})
            raw=f.assign(symbol='HIDDEN',basis='split',source='synthetic')
            meta={'split_assignment':'train' if decision.year==2024 else 'validation','membership_status':'confirmed_member','shape_readiness_status':'READY','ohlcv_hash':canonical_hash(raw),'normalized_hash':canonical_hash(f),'dataset_version':'synthetic-v1'}
            return ShapeWindow(meta,raw,f)
    config={'version':'test-v2','output_dir':'data/vision-research/pilot-v1','pilot':{'seed':7,'single_count':12,'pair_count':8,'repeat_fraction':.1,'window_lengths':[60,126],'allowed_splits':['train','validation']},'label_studio':{'document_root':'data','local_files_prefix':'/data/local-files/?d=vision-research/pilot-v1'},'anchors':[]}
    p=root/'config.yaml';p.write_text(yaml.safe_dump(config),encoding='utf-8')
    with patch('radar.vision.labeling.shape_research_universe_v1',return_value=FakeAPI()):
        build_label_studio_bundle(root,p)
    assert file_hash(dbpath)==source_hash
    return root/'data/vision-research/pilot-v1',p

def test_synthetic_bundle_is_verified_and_source_read_only(synthetic_bundle):
    result=verify(synthetic_bundle[0])
    assert result['status']=='PASS' and result['canonical_windows_verified']==24
    assert result['source_read_only_and_unchanged']

def test_pair_sampling_covers_both_splits_and_lengths(synthetic_bundle):
    p=pd.read_parquet(synthetic_bundle[0]/'pair-manifest.parquet')
    assert set(p.split_assignment)=={'train','validation'}
    assert set(p.window_length)=={60,126}

def test_repeat_ids_do_not_reveal_repeat_status(synthetic_bundle):
    m=pd.read_parquet(synthetic_bundle[0]/'sample-manifest.parquet')
    assert m.task_id.str.match('single-[0-9a-f]{24}$').all()
    assert m.task_id.nunique()==len(m)
    assert m.blind_id.nunique()==12

def test_pair_only_export_has_no_single_repeat_comparison(synthetic_bundle):
    from radar.vision.labeling import repeat_consistency
    labels=pd.DataFrame([{'task_id':'pair-smoke','task_kind':'pair','preference':'都不好'}])
    manifest=pd.read_parquet(synthetic_bundle[0]/'sample-manifest.parquet')
    result=repeat_consistency(labels,manifest)
    assert result['repeat_groups']==1
    assert result['comparable']==0 and result['agreement'] is None

def test_fixed_renderer_canvas_has_clear_uncropped_border():
    f=pd.DataFrame({'date':pd.bdate_range('2024-01-01',periods=60),'open':1.,'high':2.,'low':.5,'close':1.5,'volume':1.})
    data,_=render_blind_png(f)
    with Image.open(BytesIO(data)) as image:
        assert image.size==(960,720)
        pixels=np.array(image.convert('RGB'))
        assert (pixels[:20]==255).all() and (pixels[-20:]==255).all()
        assert (pixels[:,:20]==255).all() and (pixels[:,-20:]==255).all()

@pytest.mark.parametrize('attack',['duplicate_task','extra_visible_key','wrong_image','receipt_count','same_security_pair','repeat_mapping','image_bytes','canonical_window'])
def test_verifier_rejects_bundle_tampering(synthetic_bundle,tmp_path,attack):
    bundle=tmp_path/'bundle';shutil.copytree(synthetic_bundle[0],bundle)
    receipt=json.loads((bundle/'bundle-receipt.json').read_text(encoding='utf-8'))
    if attack in {'duplicate_task','extra_visible_key','wrong_image'}:
        path=bundle/'label-studio-single-tasks.json';tasks=json.loads(path.read_text())
        if attack=='duplicate_task':tasks.append(tasks[0])
        elif attack=='extra_visible_key':tasks[0]['data']['company_name']='HIDDEN'
        else:tasks[0]['data']['image']=tasks[1]['data']['image']
        path.write_text(json.dumps(tasks),encoding='utf-8')
        receipt['artifact_hashes'][path.name]=file_hash(path)
    elif attack=='receipt_count':receipt['single_unique']+=1
    elif attack=='same_security_pair':
        path=bundle/'pair-manifest.parquet';p=pd.read_parquet(path)
        p.loc[0,'right_task_id']=p.loc[0,'left_task_id'];p.to_parquet(path,index=False)
        receipt['artifact_hashes'][path.name]=file_hash(path)
    elif attack=='repeat_mapping':
        path=bundle/'sample-manifest.parquet';m=pd.read_parquet(path)
        m.loc[m.task_kind=='single_repeat','repeat_group']='b'*24;m.to_parquet(path,index=False)
        receipt['artifact_hashes'][path.name]=file_hash(path)
    elif attack=='image_bytes':
        path=next((bundle/'images').glob('*.png'));path.write_bytes(b'corrupt')
    else:
        path=next((bundle/'windows').glob('*-normalized.parquet'));f=pd.read_parquet(path)
        f.loc[0,'close']+=1;f.to_parquet(path,index=False)
    (bundle/'bundle-receipt.json').write_text(json.dumps(receipt),encoding='utf-8')
    with pytest.raises(ValueError):verify(bundle)

@pytest.mark.parametrize('field',['future_return','MFE','MAE','strategy2_score','symbol','security_id'])
def test_renderer_rejects_non_ohlcv_inputs(field):
    f=pd.DataFrame({'date':pd.bdate_range('2024-01-01',periods=2),'open':[1,1],'high':[2,2],'low':[.5,.5],'close':[1,1],'volume':[1,1],field:[1,1]})
    with pytest.raises(ValueError,match='only canonical'):render_blind_png(f)

@pytest.mark.parametrize('split',['test','fresh_oos'])
def test_config_rejects_test_and_fresh(synthetic_bundle,tmp_path,split):
    c=yaml.safe_load(synthetic_bundle[1].read_text());c['pilot']['allowed_splits']=[split]
    p=tmp_path/'config.yaml';p.write_text(yaml.safe_dump(c))
    with pytest.raises(ValueError,match='Train/Validation'):load_config(p)

def test_manifest_rejects_unknown_and_future_field(synthetic_bundle):
    from radar.vision.contracts import validate_sample_manifest
    m=pd.read_parquet(synthetic_bundle[0]/'sample-manifest.parquet')
    for bad in [m.assign(membership_status='unknown'),m.assign(future_return=1)]:
        with pytest.raises(Exception):validate_sample_manifest(bad)

@pytest.mark.parametrize('attack',['unknown_choice','unknown_field','multiple_choice','duplicate_task','wrong_image','smoke_as_human'])
def test_export_rejects_invalid_label_results(synthetic_bundle,tmp_path,attack):
    bundle=synthetic_bundle[0];task=json.loads((bundle/'label-studio-single-tasks.json').read_text())[0]
    task['annotations']=[{'completed_by':1,'created_at':'2026-10-08T00:00:00Z','result':[{'from_name':'overall_setup','value':{'choices':['一般']}},{'from_name':'confidence','value':{'choices':['高']}}]}]
    if attack=='unknown_choice':task['annotations'][0]['result'][0]['value']['choices']=['WRONG']
    elif attack=='multiple_choice':task['annotations'][0]['result'][0]['value']['choices']=['一般','很喜欢']
    elif attack=='unknown_field':task['data']['future_return']=1
    elif attack=='wrong_image':task['data']['image']='foreign.png'
    elif attack=='smoke_as_human':task['meta']={'label_origin':'smoke'}
    payload=[task,task] if attack=='duplicate_task' else [task]
    p=tmp_path/'export.json';p.write_text(json.dumps(payload,ensure_ascii=False),encoding='utf-8')
    with pytest.raises(ValueError):import_label_studio_export(p,bundle/'sample-manifest.parquet')

"""Causal, contract and persistence gates for Box Labeling v1."""
import json
from hashlib import sha256
from pathlib import Path
import numpy as np
import pandas as pd
import pytest
from radar.box_labeling.numeric import scales,numeric_bundle,digest,canonical
from radar.box_labeling.render import render_bundle
from radar.box_labeling.candidate_plugins.loose_box_v1 import evaluate
from radar.box_labeling.dataset import classify,packed
from radar.box_labeling.store import BoxStore,GateError,LABEL_VERSION
from radar.box_labeling.trainer import load_export,class_weights,calibration
from radar.box_labeling.verify import verify_bundle

CFG={'sessions':126,'min_width':.08,'min_occupancy':.52,'min_turns':2,
     'max_abs_drift':.65,'min_position':-.20}


def frame(n=430):
    d=pd.bdate_range('2023-01-02',periods=n)
    center=100+8*np.sin(np.arange(n)/12)
    return pd.DataFrame({'date':d,'open':center-.2,'high':center+1,'low':center-1,
                         'close':center+.2,'volume':1_000_000+np.arange(n)*30})


def signature(f,day):
    source=f.loc[f.date.le(day)].copy()
    b=numeric_bundle(f,day)
    c=evaluate(source.tail(126).reset_index(drop=True),CFG)
    r=render_bundle(b)
    return c,b,{k:v['sha256'] for k,v in r.items()}


def test_future_mutation_changes_nothing_before_t():
    f=frame();day=f.date.iloc[280]
    first=signature(f,day)
    f.loc[f.date.gt(day),['open','high','low','close','volume']]=[900,999,800,950,9e9]
    second=signature(f,day)
    assert first[0]==second[0]
    assert first[2]==second[2]
    for k in ('daily','weekly','monthly'):
        assert first[1]['scales'][k]['raw_hash']==second[1]['scales'][k]['raw_hash']
        assert first[1]['scales'][k]['tensor_hash']==second[1]['scales'][k]['tensor_hash']
        assert np.array_equal(first[1]['scales'][k]['tensor'],second[1]['scales'][k]['tensor'])


def test_partial_week_and_month_end_exactly_at_t():
    f=frame();day=pd.Timestamp('2023-03-15')
    f.loc[f.date.gt(day),'close']=800
    s=scales(f,day)
    assert s['weekly'].date.iloc[-1]==day
    assert s['monthly'].date.iloc[-1]==day
    assert s['weekly'].close.iloc[-1]==f.loc[f.date.eq(day),'close'].iloc[0]
    assert s['monthly'].high.iloc[-1]==f.loc[f.date.dt.month.eq(3)&f.date.le(day),'high'].max()


def test_plugin_deterministic_and_independent_of_future():
    f=frame().tail(126).reset_index(drop=True)
    assert evaluate(f,CFG)==evaluate(f,CFG)
    assert classify(evaluate(f,CFG)) in ('positive','boundary','control')
    with pytest.raises(ValueError):evaluate(f.assign(future_return=99),CFG)


def test_causal_price_rescaling_leaves_normalized_prices_equal():
    f=frame();day=f.date.iloc[-1]
    first=numeric_bundle(f,day)
    for key in ('open','high','low','close'):f[key]*=5
    second=numeric_bundle(f,day)
    for scale in ('daily','weekly','monthly'):
        assert np.array_equal(first['scales'][scale]['tensor'],second['scales'][scale]['tensor'])


def fixture_bundle(tmp_path):
    root=tmp_path/'bundle';root.mkdir();(root/'charts').mkdir();(root/'numeric').mkdir();(root/'raw').mkdir()
    f=frame();day=f.date.iloc[-1];b=numeric_bundle(f,day);renders=render_bundle(b)
    scales_meta={}
    for scale,item in b['scales'].items():
        svg=renders[scale]['svg'].encode();svgname=f'x-{scale}.svg';npyname=f'x-{scale}.npy'
        (root/'charts'/svgname).write_bytes(svg)
        np.save(root/'numeric'/npyname,item['tensor'],allow_pickle=False)
        rawname=f'x-{scale}.json';(root/'raw'/rawname).write_bytes(canonical(item['raw']))
        scales_meta[scale]={'chart_file':svgname,'chart_hash':digest(svg),
                            'tensor_file':npyname,'tensor_hash':item['tensor_hash'],
                            'raw_file':rawname,'raw_hash':item['raw_hash'],'available':item['available'],
                            'length':item['length']}
    row={'task_id':'taskx','security_id':'historical-security','decision_date':str(day.date()),
         'split':'train','stratum':'positive','candidate_score':.7,
         'scales':scales_meta,'normalization_version':b['version'],
         'candidate_plugin_version':'loose-box-v1','config_hash':'fixture'}
    raw=packed([row]);(root/'manifest.json').write_bytes(raw)
    (root/'receipt.json').write_bytes(packed({'version':'box-label-tasks-v1','manifest_hash':digest(raw)}))
    return root


def test_human_payload_and_revision_export_isolation(tmp_path):
    root=fixture_bundle(tmp_path)
    assert verify_bundle(root)['tasks']==1
    human=BoxStore(root,'human');smoke=BoxStore(root,'smoke')
    visible=human.task('taskx',1)
    assert set(visible)=={'task_id','charts','coverage','revision','label','label_version'}
    assert 'historical-security' not in json.dumps(visible)
    assert 'candidate_score' not in json.dumps(visible)
    assert all('svg' in x for x in visible['charts'].values())
    payload={'shape':'BOX','position':'LOWER','confidence':'MEDIUM','reasons':[],
             'note':'','expected_revision':0,'label_version':LABEL_VERSION}
    assert smoke.save('taskx',1,payload)['revision']==1
    assert human.task('taskx',1)['revision']==0
    with pytest.raises(GateError,match='stale'):smoke.save('taskx',1,payload)
    bad=dict(payload,expected_revision=1,shape='UP')
    with pytest.raises(GateError,match='choice'):smoke.save('taskx',1,bad)
    assert smoke.save('taskx',1,dict(payload,expected_revision=1,position='MIDDLE'))['revision']==2
    result=smoke.export_numeric(1,root/'export.json')
    assert result['examples']==1
    export=json.loads((root/'export.json').read_bytes())
    assert 'future' not in json.dumps(export).lower()
    assert 'chart' not in json.dumps(export).lower()
    assert len(load_export(root/'export.json'))==1
    export['examples'].append(dict(export['examples'][0],split='validation'))
    (root/'bad-split.json').write_bytes(packed(export))
    with pytest.raises(ValueError,match='overlaps'):load_export(root/'bad-split.json')
    (root/'raw'/'x-daily.json').write_text('[]')
    with pytest.raises(GateError,match='raw'):smoke.export_numeric(1,root/'another-export.json')


def test_current_private_batch_controls_and_hashes_if_present():
    root=Path(__file__).resolve().parents[1]/'data/box-label-v1-2m-1y-4y'
    if not (root/'manifest.json').exists():pytest.skip('private batch unavailable')
    report=verify_bundle(root)
    assert report['strata']=={'control':3,'positive':21,'boundary':6}
    assert report['tasks']==report['unique_securities']==30


def test_synthetic_only_trainer_contract(tmp_path):
    pytest.importorskip('torch')
    from radar.box_labeling.trainer import fit_numeric_export
    root=fixture_bundle(tmp_path);store=BoxStore(root,'smoke')
    payload={'shape':'BOX','position':'LOWER','confidence':'HIGH','reasons':[],
             'note':'synthetic fixture','expected_revision':0,'label_version':LABEL_VERSION}
    store.save('taskx',1,payload);store.export_numeric(1,root/'synthetic.json')
    export=json.loads((root/'synthetic.json').read_bytes())
    export['examples'].append(dict(export['examples'][0],sample_id='other',
                                   security_id='synthetic-validation-security',split='validation',
                                   shape_label='NOT_BOX',position_label='UPPER'))
    (root/'synthetic-two-split.json').write_bytes(packed(export))
    result=fit_numeric_export(root/'synthetic-two-split.json',root/'synthetic-checkpoint.pt',epochs=1)
    assert result['metadata']['train_count']==result['metadata']['validation_count']==1
    assert result['validation_metrics']['shape_calibration']['bins']==10
    assert (root/'synthetic-checkpoint.pt').exists()
    with pytest.raises(ValueError):class_weights({'BOX':1},('BOX','NOT_BOX'))


def test_real_provider_boundary_if_local_data_available():
    root=Path(__file__).resolve().parents[2]/'stock-radar'
    private=root/'config/research_infrastructure_v1.json'
    if not private.exists():pytest.skip('frozen local research store unavailable')
    from radar.box_labeling.history import BoxHistory
    with BoxHistory(root) as provider:
        row=provider.api.core.connection.execute('''SELECT security_id,decision_date FROM universe_window_index
             WHERE length=126 AND supported_membership AND shape_research_ready
             AND decision_date BETWEEN DATE '2023-01-01' AND DATE '2023-12-31' LIMIT 1''').fetchone()
        h=provider.history(*row)
        assert h.date.max()==pd.Timestamp(row[1])
        assert h.date.le(pd.Timestamp(row[1])).all()
        with pytest.raises(ValueError):provider.history(row[0],'2026-10-01')

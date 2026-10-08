import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from radar.pit.features import file_hash
from radar.pit.shape import render_svg,tensor
from radar.research.infrastructure import (ResearchInfrastructure, fresh_decision, reject_future_benchmark,
                                           semantic_hash,validate_freeze,validate_input)
from test_shape_research import built


@pytest.fixture(scope='module')
def infrastructure(built):
    root,core,days,_=built
    fresh=root/'data/pit/shape-research/fresh-oos/fixture';fresh.mkdir(parents=True)
    start=days[610].date()
    c=duckdb.connect(str(fresh/'fresh.duckdb'))
    c.execute("ATTACH '"+str(core/'shape.duckdb').replace("'","''")+"' AS core (READ_ONLY)")
    cols='security_id,symbol,date,open,high,low,close,volume,source,basis,source_hash,shape_research_ready,shape_research_status,membership_status'
    c.execute(f"CREATE TABLE prices AS SELECT {cols} FROM core.shape_price WHERE security_id IN ('S','U')")
    c.execute('CREATE TABLE fresh_price AS SELECT * FROM prices WHERE date>=?',[start])
    c.execute("CREATE TABLE fresh_window_index AS SELECT * FROM core.universe_window_index WHERE security_id IN ('S','U') AND decision_date>=?",[start])
    c.close()
    sem={'fresh_start':str(start),'core_database_sha256':file_hash(core/'shape.duckdb'),'fresh_database_sha256':file_hash(fresh/'fresh.duckdb')}
    profile={'semantics':sem,'semantic_hash':semantic_hash(sem),'core_directory':core.relative_to(root).as_posix(),'fresh_directory':fresh.relative_to(root).as_posix()}
    path=root/'config/research_infrastructure_v1.json';path.write_text(json.dumps(profile),encoding='utf8')
    return root,days,profile


@pytest.fixture
def api(infrastructure):
    with ResearchInfrastructure(infrastructure[0]) as db:yield db


@pytest.mark.parametrize('length',[20,40,60,126])
def test_pre_fresh_lookback_allowed(api,infrastructure,length):
    days=infrastructure[1];w=api.window('S',days[610],length)
    assert len(w.ohlcv)==length and w.metadata['split_assignment']=='fresh_oos'
    assert w.ohlcv.date.min()<days[610] and w.ohlcv.date.max()==days[610]
    assert 'S' in set(api.universe_on(days[610],length).security_id)


def test_post_decision_bars_rejected(api,infrastructure):
    w=api.window('S',infrastructure[1][610],20)
    bad=w.ohlcv.copy();bad.loc[bad.index[-1],'date']=infrastructure[1][611]
    with pytest.raises(ValueError):validate_input(bad,infrastructure[1][610])


def test_future_labels_rejected(api,infrastructure):
    w=api.window('S',infrastructure[1][610],20)
    with pytest.raises(ValueError):validate_input(w.ohlcv.assign(future_return=1),infrastructure[1][610])


def test_future_predictive_metadata_rejected(api,infrastructure):
    w=api.window('S',infrastructure[1][610],20)
    with pytest.raises(ValueError):validate_input(w.ohlcv.assign(future_membership=True),infrastructure[1][610])


def test_fresh_decision_date_required(api,infrastructure):
    day=infrastructure[1][599]
    assert not fresh_decision(day,api.profile['semantics']['fresh_start'])
    with pytest.raises(ValueError,match='Fresh decision'):api.evaluation_window('S',day,20,{})
    assert api.window('S',day,20).metadata['split_assignment']=='test'


def freeze_fixture(tmp_path):
    model=tmp_path/'model.txt';parameters=tmp_path/'parameters.json'
    model.write_text('frozen fixture');parameters.write_text('{}')
    receipt={'recorded_at':'2026-09-28T00:00:00Z','model_frozen_at':'2026-09-28T00:00:00Z',
             'parameters_frozen_at':'2026-09-28T00:00:00Z','used_fresh_outcomes_for_tuning':False,
             'model':{'path':str(model),'sha256':file_hash(model)},'parameters':{'path':str(parameters),'sha256':file_hash(parameters)}}
    return receipt


def test_model_freeze_must_precede_f(tmp_path):
    receipt=freeze_fixture(tmp_path);assert validate_freeze(receipt,'2026-09-29')
    receipt['model_frozen_at']='2026-09-29T12:00:00Z'
    with pytest.raises(ValueError):validate_freeze(receipt,'2026-09-29')


def test_parameter_freeze_must_precede_f(tmp_path):
    receipt=freeze_fixture(tmp_path);receipt['parameters_frozen_at']='2026-10-08T00:00:00Z'
    with pytest.raises(ValueError):validate_freeze(receipt,'2026-09-29')


def test_missing_freeze_denies_evaluation(api,infrastructure):
    with pytest.raises(ValueError,match='complete dated'):api.evaluation_window('S',infrastructure[1][610],126,{})


def test_parameters_cannot_mutate_from_test(tmp_path):
    receipt=freeze_fixture(tmp_path);Path(receipt['parameters']['path']).write_text('{"test_score":999}')
    with pytest.raises(ValueError,match='changed'):validate_freeze(receipt,'2026-09-29')


def test_fresh_tuning_explicitly_denied(tmp_path):
    receipt=freeze_fixture(tmp_path);receipt['used_fresh_outcomes_for_tuning']=True
    with pytest.raises(ValueError,match='tune'):validate_freeze(receipt,'2026-09-29')


def test_future_benchmark_rejected(api,infrastructure):
    days=infrastructure[1];benchmark=pd.Series(100.,index=days)
    with pytest.raises(ValueError,match='benchmark'):api.strategy2_feature_window('S',days[610],benchmark,benchmark)
    result=api.strategy2_feature_window('S',days[610],benchmark.loc[:days[610]],benchmark.loc[:days[610]])
    assert result.index.names==['date','symbol']


def test_unknown_evidence_not_false_or_future_projected(api,infrastructure):
    day=infrastructure[1][610]
    assert 'U' not in set(api.universe_on(day).security_id)
    assert 'U' in set(api.universe_on(day,include_unknown=True).security_id)
    w=api.window('U',day,20,include_unknown=True)
    assert w.metadata['membership_status']=='unknown'
    assert set(w.normalized.columns)=={'date','open','high','low','close','volume'}


def test_fresh_cannot_return_to_training(api,infrastructure):
    w=api.window('S',infrastructure[1][610],126)
    with pytest.raises(ValueError):w.training_tensor()


def test_determinism_corrected_fresh_window(api,infrastructure):
    a=api.window('S',infrastructure[1][610],126);b=api.window('S',infrastructure[1][610],126)
    assert a.metadata['ohlcv_hash']==b.metadata['ohlcv_hash']
    assert render_svg(a.normalized)==render_svg(b.normalized)
    assert tensor(a.normalized).tobytes()==tensor(b.normalized).tobytes()


def test_lazy_constructor_does_not_open_strict_or_shape(infrastructure):
    with ResearchInfrastructure(infrastructure[0]) as api:
        assert api._core is None and api._fresh is None


def test_frozen_configuration_semantic_mutation_rejected(infrastructure,tmp_path):
    r=tmp_path;r.joinpath('config').mkdir()
    p=json.loads(json.dumps(infrastructure[2]));p['semantics']['fresh_start']='2021-01-01'
    r.joinpath('config/research_infrastructure_v1.json').write_text(json.dumps(p))
    with pytest.raises(ValueError,match='mutated'):ResearchInfrastructure(r)


def test_archive_never_default_import_or_discovery():
    root=Path(__file__).resolve().parents[1]
    assert 'archive/' not in (root/'pyproject.toml').read_text()
    code=(root/'src/radar/research/infrastructure.py').read_text()
    assert 'rglob(' not in code and "glob(" not in code


def cleanup_function():
    import importlib.util
    p=Path(__file__).resolve().parents[1]/'scripts/inventory_database_assets.py'
    spec=importlib.util.spec_from_file_location('inventory_database_assets',p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    return m.cleanup_eligible


def test_cleanup_referenced_published_and_blocked_kept(tmp_path):
    f=tmp_path/'derived.duckdb';f.write_bytes(b'fixture')
    record={'path':f.name,'category':'E','recommended_action':'DELETE_CANDIDATE','current_references':[],
            'reproducible':True,'source_still_available':True,'sha256':file_hash(f)}
    eligible=cleanup_function();assert eligible(record,tmp_path)
    assert not eligible({**record,'current_references':['current.json']},tmp_path)
    assert not eligible({**record,'recommended_action':'POLICY_BLOCKED_KEEP'},tmp_path)
    assert not eligible({**record,'strict_pit_evidence_dependency':True},tmp_path)
    (tmp_path/'manifest.json').write_text('{}');assert not eligible(record,tmp_path)


def test_cleanup_hash_drift_and_outside_workspace_kept(tmp_path):
    f=tmp_path/'derived.duckdb';f.write_bytes(b'fixture')
    record={'path':f.name,'category':'E','recommended_action':'DELETE_CANDIDATE','current_references':[],
            'reproducible':True,'source_still_available':True,'sha256':'0'*64}
    eligible=cleanup_function();assert not eligible(record,tmp_path)
    assert not eligible({**record,'path':'../outside.duckdb'},tmp_path)

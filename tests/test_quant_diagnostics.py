import json
from types import SimpleNamespace
import duckdb
import pandas as pd
import pytest
from radar.research.quant_diagnostics import candidate_diagnostics,portfolio_diagnostics
from radar.research.sessions import calendar


def test_actual_sizing_addback_is_not_a_counterfactual_portfolio():
    result={'equity':[{'equity':1000.},{'equity':1080.}],
        'trades':[{'net_return':.08,'entry_fee':3.,'exit_fee':4.,'slippage_cost':13.,'exit_date':'2024-02-05'}]}
    r=portfolio_diagnostics(result,1000.)
    assert r['actual_sizing_cost_attribution']['reference_price_return_addback']==pytest.approx(.1)
    assert r['actual_sizing_cost_attribution']['net_pnl']==80.
    assert r['exit_years']=={'2024':1}


def test_same_frozen_background_and_raw_split_censoring_without_candidate_refill(tmp_path,monkeypatch):
    from radar.research import quant_diagnostics as module
    days=calendar().sessions_in_range('2025-02-03','2025-02-20')
    root=tmp_path;private=root/'data'/'pilot';private.mkdir(parents=True)
    private.joinpath('audit.json').write_text('{}')
    rows=[dict(method='q1_fuzzy_shape',status='qualified',security_id=sid,symbol=sid,
        decision_date=str(days[0].date()),rank=rank,provenance={'series_id':sid})
        for rank,sid in enumerate(['safe','split'],1)]
    private.joinpath('candidates.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
    core=duckdb.connect(':memory:')
    eligible=pd.DataFrame([dict(security_id=sid,decision_date=days[0],series_id=sid,basis='raw',
        length=126,supported_membership=True,priority=1) for sid in ['safe','split']])
    bars=pd.DataFrame([dict(series_id=sid,date=d,open=100.,high=106.,low=99.,shape_research_ready=True,
        identity_conflict=False,class_or_name_boundary=False) for sid in ['safe','split'] for d in days])
    core.register('eligible',eligible);core.register('bars',bars)
    core.execute('create table universe_window_index as select * from eligible')
    core.execute('create table shape_price as select * from bars')
    core.execute('create table split_action(security_id varchar,date date)')
    core.execute('insert into split_action values (?,?)',['split',days[4].date()])
    class API:
        def __init__(self,root):self.core=SimpleNamespace(connection=core)
        def __enter__(self):return self
        def __exit__(self,*args):pass
    monkeypatch.setattr(module,'ResearchInfrastructure',API)
    with duckdb.connect(str(root/'data/market.duckdb')) as c:
        spy=pd.DataFrame({'date':days,'close':100.,'symbol':'SPY'})
        c.register('spy',spy);c.execute('create table daily_bars as select * from spy')
    result=candidate_diagnostics(root,private,[str(days[0].date()),str(days[0].date()),str(days[-1].date())])
    metrics=result['methods']['q1_fuzzy_shape']['metrics']
    assert metrics['candidate_count']==2 and metrics['censored_candidate_count']==1
    assert metrics['labeled_background_count']==1 and metrics['base_rate']==1.
    assert metrics['precision_at_10']==1. and metrics['top_10_count']==1
    assert metrics['event_top_10_count']==1
    assert result['methods']['q2_parallel_channel']['metrics']['precision_at_10'] is None
    assert result['background_exclusions']=={'raw_split_crosses_outcome_horizon':1}
    assert private.joinpath('q1_fuzzy_shape-diagnostic-labels.parquet').exists()
    core.close()

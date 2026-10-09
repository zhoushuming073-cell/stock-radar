"""Q1 parity, causal Q2 fixes, exchange-date/current boundaries and native close execution."""
from pathlib import Path
import importlib.util
import json
import os
import numpy as np
import pandas as pd
import pytest
from hypothesis import given, strategies as st
from radar.research.candidates import configurations, q1, fingerprint
from radar.research.fuzzy_shape import array_features, features_at
from radar.vision import quant_features as accepted
from radar.research.parallel_channel import ChannelSettings,_daily,consensus,analyze,_aggregate
from radar.research.sessions import calendar,completed_session,require_session
from radar.research.daily import save_snapshot,load_latest,current_inputs

ROOT=Path(__file__).resolve().parents[1]
CFG,_=configurations(ROOT)

def candles(n=450,kind='range'):
    t=np.arange(n,dtype=float)
    c=40+6*np.sin(2*np.pi*t/56) if kind=='range' else 40*np.exp((.004 if kind=='up' else -.004)*t)
    dates=calendar().sessions_in_range('2023-01-03','2025-12-31')[:n]
    return pd.DataFrame({'date':dates,'open':c*.998,'high':c*1.01,'low':c*.99,'close':c,'volume':1000000.})

@pytest.mark.parametrize('n',[60,126])
@given(seed=st.integers(0,100000))
def test_q1_exact_accepted_parity(n,seed):
    rng=np.random.default_rng(seed);c=np.exp(rng.normal(0,.035,n).cumsum())*100
    a=np.column_stack([c*.995,c*1.02,c*.98,c,rng.integers(0,1000000,n)])
    assert array_features(a,CFG)==accepted.array_features(a,CFG)

def test_q1_current_production_namespace_has_no_vision_dependency():
    import radar.research.candidates as module
    assert 'radar.vision' not in Path(module.__file__).read_text()
    assert 'radar.vision' not in (ROOT/'src/radar/research/fuzzy_shape.py').read_text()

@pytest.mark.parametrize('kernel',[features_at,accepted.features_at])
def test_q1_future_invariance(kernel):
    f=candles(126);future=candles(145);future.loc[126:,['open','high','low','close','volume']]*=999
    assert kernel(f,f.date.iloc[-1],CFG)==kernel(future,f.date.iloc[-1],CFG)

def test_q1_extension_and_observe_are_independent_status_dimensions():
    f=candles(126);r=q1(f,str(f.date.iloc[-1].date()),CFG,security_id='fixture',symbol='AAA')
    assert r.method=='q1_fuzzy_shape'
    assert set(r.subscores)==set(accepted.DIMENSIONS)
    assert r.provenance=={} and 'outcome' not in r.model_dump()

def test_q2_future_invariance_including_partial_buckets():
    f=candles();t=f.date.iloc[-16]
    changed=f.copy();changed.loc[changed.date>t,['open','high','low','close','volume']]*=50
    assert analyze(f,t)==analyze(changed,t)

@pytest.mark.parametrize('kind',['up','down'])
def test_monotonic_is_not_channel_or_daily_cycle(kind):
    f=candles(kind=kind);r=analyze(f,f.date.iloc[-1])
    assert not r['qualified']
    assert not _daily(f,20,100,ChannelSettings())['cycle_detected']

def test_noise_without_meaningful_impulse_is_not_cycle():
    f=candles(126);f[['open','high','low','close']]=np.tile([40,40.02,39.98,40],(126,1))
    assert not _daily(f,35,45,ChannelSettings())['cycle_detected']

def test_partial_week_and_month_no_future_asof_date():
    f=candles();t=pd.Timestamp('2024-09-18');f=f[f.date<=t]
    for freq in ['W-FRI','ME']:
        r=_aggregate(f,freq).iloc[-1]
        assert r.date==t and r.observed_through==t and r.bucket_end>=t and r.partial

def test_log_coordinate_and_undercut_penalty():
    f=candles(126);f.loc[f.index[-1],'close']=40
    cfg=ChannelSettings()
    r=_daily(f,20,80,cfg)
    assert r['channel_position']==pytest.approx(.5)
    def d(price):
        x=f.copy();x.loc[x.index[-1],'close']=price
        return _daily(x,40,80,cfg)
    assert d(40)['distance_score']>d(39)['distance_score']>d(38)['distance_score']
    assert d(35)['stage']=='breakdown'

def channel(lower=40,upper=60,position=.2,slope=0,quality=80):
    return dict(eligible=True,lower=lower,upper=upper,position=position,slope=slope,timeframe='weekly',quality=quality)

def test_lucky_best_window_does_not_qualify():
    c=ChannelSettings()
    assert not consensus([channel()],c)['stable']
    assert consensus([channel(),channel()],c)['stable']
    assert not consensus([channel(),channel(lower=20,upper=100,position=.8)],c)['stable']

@pytest.mark.parametrize('day',['2026-10-10','2026-12-25'])
def test_nonexchange_or_future_asof_rejected(day):
    with pytest.raises(ValueError):require_session(day,now='2026-10-09T00:00:00Z')

def test_completed_date_weekend_holiday_and_inprogress():
    assert completed_session('2026-10-10T12:00:00Z')=='2026-10-09'
    assert completed_session('2026-12-25T22:00:00Z')=='2026-12-24'
    assert completed_session('2026-10-08T19:00:00Z')=='2026-10-07'

def test_immutable_daily_snapshot_empty_is_valid_and_replay_is_persistent(tmp_path):
    r={'as_of':'2026-10-08','q1_all':[],'q2_all':[],'overlap':[]}
    a=save_snapshot(tmp_path,r);b=save_snapshot(tmp_path,r)
    assert a==b
    x=load_latest(tmp_path,now='2026-10-10T12:00:00Z')
    assert x['q1']==[] and x['stale'] and x['freshness']=='STALE'

def test_invalid_top_and_method():
    from radar.research.daily import snapshot
    for method,top in [('bogus',20),('all',0),('q1',101),('q2',True)]:
        with pytest.raises(ValueError):snapshot(ROOT,method=method,top=top)

@pytest.mark.parametrize('early_close',[False,True])
def test_native_fixed_tenth_session_close(tmp_path,early_close):
    if os.environ.get('STOCK_RADAR_TEST_LEAN')!='1':pytest.skip('actual native LEAN opt-in')
    from radar.lean.runtime import installation,invoke
    from radar.lean.export import prepare_bundle
    from radar.lean.result_adapter import normalize
    from radar.lab.parameters import execution_defaults_from_legacy
    from radar.backtest.costs import load_fee_config
    sessions=calendar().sessions_in_range('2025-11-13','2025-12-03') if early_close else calendar().sessions_in_range('2025-02-03','2025-02-20')
    prices=pd.DataFrame([{'symbol':s,'date':d,'open':100+i,'close':100+i+.5,
                         'high':102+i,'low':99+i,'volume':1000000}
                        for s in ['AAA','SPY'] for i,d in enumerate(sessions)])
    signals=[dict(symbol='AAA',signal_date=str(sessions[0].date()),rank=1,strategy_score=80,
                  strategy_id='horizon_fixture',strategy_version='1',reference_close=100.5,
                  avg_dollar_volume_20=100000000,allocation_weight=1)]
    metadata=dict(strategy_id='horizon_fixture',strategy_version='1',
                  window=[str(sessions[0].date()),str(sessions[0].date()),str(sessions[-1].date())])
    execution=execution_defaults_from_legacy({'initial_capital':100000,'max_new_candidates':10,
        'take_profit':None,'stop_loss':None,'max_holding_sessions':10,'entry_gap_min':-.1,
        'entry_gap_max':.05,'max_position_fraction':1,'minimum_position_fraction':0,
        'max_order_to_avg_dollar_volume':.02,'allocator':'equal_cash','market_guard':'none'},
        slippage_bps=10,execution_timing='next_open')
    execution['entry_gap']['enabled']=False;execution['exit']['timing']='fixed_horizon_close'
    execution['sizing']['cash_allocation']='equal_remaining_slots'
    home,identity=installation(ROOT);out=tmp_path/'native'
    path=prepare_bundle(home,out,metadata,list(sessions),signals,prices,execution,
                        load_fee_config(ROOT/'config/research.yaml'),max_positions=10)
    raw=invoke(ROOT,out,path,'horizon_fixture',lambda row:None,lambda:False,expected_identity=identity)
    result,metrics=normalize(out,raw,identity)
    assert len(result['trades'])==1
    trade=result['trades'][0]
    assert trade['signal_date']==str(sessions[0].date())
    assert trade['entry_date']==str(sessions[1].date())
    assert trade['exit_date']==str(sessions[10].date()) and trade['holding_sessions']==10
    assert trade['exit_reason']=='fixed_horizon_close'
    assert pd.Timestamp(trade['exit_time']).tz_convert('America/New_York').hour==(13 if early_close else 16)
    assert trade['exit_price']==pytest.approx((110.5)*(1-.001))
    assert not result['open_positions']

def test_freeze_receipt_can_be_reopened_without_tuple_list_drift(tmp_path,monkeypatch):
    from radar.research import quant_lean
    monkeypatch.setattr(quant_lean,'installation',lambda root:(tmp_path,{'engine':'lean','commit':'test_fixture'}))
    before=quant_lean.freeze(ROOT,tmp_path/'receipt')
    after=quant_lean.freeze(ROOT,tmp_path/'receipt')
    assert before==after
    assert after['research_config']['top_k']==10
    assert after['Fresh']=='NOT_RUN'

def test_execution_display_retains_native_policy_and_is_finite_json():
    from radar.research.quant_lean import execution_config,execution_display
    import yaml
    cfg=yaml.safe_load((ROOT/'config/quant_research_v1.yaml').read_text())
    native=execution_config(cfg);view=execution_display(native)
    json.dumps(view,allow_nan=False)
    assert view['entry_gap_enabled'] is False
    assert view['max_holding_sessions']==10 and view['exit_timing']=='fixed_horizon_close'
    assert native['exit']['timing']=='fixed_horizon_close'

@pytest.mark.parametrize('failure',['missing','raw_split','source_switch'])
def test_preflight_blocks_unsafe_forward_prices_without_candidate_substitution(tmp_path,monkeypatch,failure):
    from radar.research import quant_lean
    import duckdb
    from types import SimpleNamespace
    days=calendar().sessions_in_range('2025-02-03','2025-02-20')
    frame=pd.DataFrame({'date':days,'open':100.,'high':101.,'low':99.,'close':100.,'volume':1000000.,
                        'series_id':'source-a','source':'fixture','basis':'raw','shape_research_ready':True,
                        'identity_conflict':False,'class_or_name_boundary':False})
    core=duckdb.connect(':memory:')
    subset=frame.drop(index=5) if failure=='missing' else frame
    core.register('input_bars',subset);core.execute('create table shape_price as select * from input_bars')
    core.execute('create table split_action (security_id varchar,date date,factor double)')
    if failure=='raw_split':core.execute('insert into split_action values (?,?,?)',['security-a',days[6].date(),2.])
    class API:
        def __init__(self,root):self.core=SimpleNamespace(connection=core)
        def __enter__(self):return self
        def __exit__(self,*args):pass
    monkeypatch.setattr(quant_lean,'ResearchInfrastructure',API)
    (tmp_path/'data').mkdir()
    with duckdb.connect(str(tmp_path/'data/market.duckdb')) as c:
        spy=frame.copy();spy['symbol']='SPY';c.register('spy',spy);c.execute('create table daily_bars as select * from spy')
    row=dict(selected=True,security_id='security-a',symbol='AAA',decision_date=str(days[0].date()),
             rank=1,score=80.,method='q1_fuzzy_shape',version='fuzzy-shape-v1',
             provenance={'series_id':'source-a','source':'fixture','basis':'raw'})
    rows=[row]
    if failure=='source_switch':
        other={**row,'provenance':{**row['provenance'],'series_id':'source-b'}};rows.append(other)
    before=json.dumps(rows,sort_keys=True)
    r=quant_lean.execution_inputs(tmp_path,rows,[str(days[0].date()),str(days[0].date()),str(days[-1].date())])
    assert r[0]['status']=='BLOCKED'
    assert r[0]['failures'][0]['reason']=={'missing':'missing_10session_fill_prices',
         'raw_split':'raw_action_requires_existing_certified_native_PIT_contract',
         'source_switch':'execution_source_switch'}[failure]
    assert r[1:4]==(None,None,None)
    assert json.dumps(rows,sort_keys=True)==before
    core.close()


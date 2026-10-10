"""Cloud package causality, source equivalence and execution transport guards."""
import ast
from dataclasses import asdict,replace
from datetime import datetime
import importlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace as N,ModuleType

import numpy as np
import pandas as pd
import pytest

from radar.research.high_beta import channel
from radar.research.high_beta.cloud.build import sources,prepare,Relocate,Q2_NAMES,CHANNEL_NAMES,sha
from radar.research.high_beta.cloud.data import QcEvidence,causal_split_window,common_identity,complete_amount
from radar.research.sessions import calendar

ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture
def generated(tmp_path,monkeypatch):
    prepare(ROOT,tmp_path);monkeypatch.syspath_prepend(str(tmp_path/'upload'))
    imports=ModuleType('AlgorithmImports')
    for name in ['QCAlgorithm','FeeModel','ImmediateFillModel']:setattr(imports,name,type(name,(),{}))
    imports.OrderFee=lambda value:N(value=value)
    imports.CashAmount=lambda amount,currency:N(amount=amount,currency=currency)
    imports.OrderStatus=N(FILLED='filled')
    imports.TradeBar=type('TradeBar',(),{});imports.Resolution=N(DAILY='daily')
    imports.DataNormalizationMode=N(RAW='raw');imports.Split=type('Split',(),{})
    imports.SplitType=N(SPLIT_OCCURRED='occurred')
    monkeypatch.setitem(sys.modules,'AlgorithmImports',imports)
    names=['main','sr_q2','sr_channel','sr_math','sr_contracts','sr_execution','sr_sessions','sr_config','sr_data','sr_fill']
    for name in names:monkeypatch.delitem(sys.modules,name,raising=False)
    loaded={name:importlib.import_module(name) for name in names}
    yield loaded
    for name in names:sys.modules.pop(name,None)


@pytest.mark.parametrize('path,target,names',[
    ('src/radar/research/high_beta/channel.py','sr_q2.py',Q2_NAMES),
    ('src/radar/research/parallel_channel.py','sr_channel.py',CHANNEL_NAMES),
    ('src/radar/features/elasticity.py','sr_math.py',('_market_model',)),
    ('src/radar/research/candidates.py','sr_contracts.py',('fingerprint',))])
def test_generated_selector_ast_matches_original(path,target,names):
    files,_=sources(ROOT)
    def nodes(source):return {n.name:n for n in ast.parse(source).body if isinstance(n,(ast.FunctionDef,ast.ClassDef))}
    original=nodes((ROOT/path).read_text(encoding='utf-8'));cloud=nodes(files[target])
    for name in names:
        assert ast.dump(Relocate().visit(original[name]),include_attributes=False)==ast.dump(cloud[name],include_attributes=False)


def test_execution_source_and_frozen_settings_are_unmodified(generated):
    files,receipt=sources(ROOT)
    assert files['sr_execution.py'].endswith((ROOT/'src/radar/lean/algorithm_fixed_horizon.py').read_text(encoding='utf-8'))
    cfg=generated['sr_config']
    assert cfg.SETTINGS==asdict(channel.settings(ROOT))
    assert cfg.EXECUTION['exit']['max_holding_sessions']==10
    assert cfg.EXECUTION['max_positions']==10 and cfg.EXECUTION['slippage_bps']==10
    assert cfg.STUDY['start']=='2021-01-04' and cfg.STUDY['end']=='2025-12-31'
    assert cfg.RECEIPT==receipt and not cfg.STUDY['parameter_optimization']


def frame(n=430):
    days=calendar().sessions_in_range('2023-01-03','2025-12-31')[:n]
    t=np.arange(n);r=.008*np.sin(t*.9)+.004*np.cos(t*.4)
    bench=100*np.cumprod(1+r);c=40*np.cumprod(1+2.8*r)
    x=pd.DataFrame(dict(date=days,open=c*.995,high=c*1.025,low=c*.975,close=c,volume=12_000_000))
    spy=pd.DataFrame(dict(date=days,close=bench))
    return x,spy


def test_full_generated_selector_equals_local_math_and_excludes_future(generated):
    x,spy=frame();t=x.date.iloc[-20];cloud=generated['sr_q2']
    expected=channel.analyze(x,t,spy,spy,QcEvidence(True,True,True))
    assert cloud.analyze(x,t,spy,spy,QcEvidence(True,True,True))==expected
    changed=x.copy();changed.loc[changed.date>t,['open','high','low','close','volume']]*=1000
    b=spy.copy();b.loc[b.date>t,'close']=.01
    assert cloud.analyze(changed,t,b,b,QcEvidence(True,True,True))==expected
    assert expected['market_qualified']


def test_export_is_deterministic_own_source_only_and_free_quota(tmp_path):
    a=prepare(ROOT,tmp_path/'a');b=prepare(ROOT,tmp_path/'b')
    assert a==b and a['upload_files']==10 and a['cloud_result'] is None
    assert (tmp_path/'a/q2-v1.2-cloud-source.zip').read_bytes()==(tmp_path/'b/q2-v1.2-cloud-source.zip').read_bytes()
    assert not a['market_data_included']
    for name,detail in a['files'].items():
        raw=(tmp_path/'a/upload'/name).read_bytes()
        assert len(raw)<=32000 and sha(raw)==detail['sha256']
        ast.parse(raw)
        assert 'forward_return_10' not in raw.decode() and 'future_outcome' not in raw.decode()


def test_unexpected_upload_file_is_rejected(tmp_path):
    prepare(ROOT,tmp_path);(tmp_path/'upload/old.py').write_text('old = True')
    with pytest.raises(ValueError,match='Unexpected upload'):prepare(ROOT,tmp_path)


@pytest.mark.parametrize('change',[{'source':'alpaca'},{'feed':'sip'},{'identity_trusted':False},
    {'common_stock':False},{'split_events_verified':False},{'joint_price_volume_adjustment':False},
    {'historical_certified':True},{'scope':'historical_verified'}])
def test_qc_domain_does_not_impersonate_local_certification(change):
    assert replace(QcEvidence(True,True,True),**change).refusal()


def test_causal_split_joint_amount_invariant_and_future_ignored():
    x,_=frame(30);day=x.date.iloc[20];t=x.date.iloc[-1]
    e=dict(effective_date=str(day.date()),event_type='split',confidence='verified',ratio=2)
    adjusted=causal_split_window(x,[e],t)
    assert np.allclose(adjusted.close*adjusted.volume,x.close*x.volume)
    future={**e,'effective_date':'2028-01-01','ratio':999}
    pd.testing.assert_frame_equal(causal_split_window(x,[e,future],t),adjusted)
    assert adjusted.loc[19,'close']==x.loc[19,'close']/2
    assert adjusted.loc[20,'close']==x.loc[20,'close']
    with pytest.raises(ValueError,match='duplicate'):causal_split_window(x,[e,e],t)
    with pytest.raises(ValueError,match='unverified'):causal_split_window(x,[{**e,'confidence':'unknown'}],t)


@pytest.mark.parametrize('kind,dr,ipo,expected',[
    ('ST00000001',False,'2010-01-01',True),('ST00000002',False,'2010-01-01',False),
    ('',False,'2010-01-01',False),('ST00000001',True,'2010-01-01',False),
    ('ST00000001',False,'2025-01-01',False),('ST00000001',False,'1900-01-01',False)])
def test_only_historical_known_common_identity(kind,dr,ipo,expected):
    f=N(has_fundamental_data=True,symbol=N(id='historical-sid'),
        security_reference=N(security_type=kind,is_depositary_receipt=dr,ipo_date=datetime.fromisoformat(ipo)))
    assert common_identity(f,'2021-01-04')==expected


def test_recent_amount_missing_sessions_cannot_be_imputed():
    x,_=frame(30);days=x.date.iloc[-20:]
    assert complete_amount(x,days)==pytest.approx(float((x.close*x.volume).tail(20).mean()))
    assert complete_amount(x.drop(x.index[-3]),days) is None


def test_moc_fee_none_reference_matches_native_schedule(generated):
    cfg=generated['sr_config'];native=generated['sr_execution'];fill=generated['sr_fill']
    a=N(key_for_symbol=lambda _:'sid',_sr_context={'sid':{'reference':None}},_sr_slip=.001,_sr_bundle={'fees':cfg.FEES})
    fee=fill.ReferenceOpenFee(a).get_order_fee(N(security=N(symbol='sid',price=50.),order=N(quantity=-100)))
    expected=native.fee_components(cfg.FEES,100,50*(1-.001),True)['total']
    assert float(fee.value.amount)==pytest.approx(expected)


def test_native_open_policy_refuses_same_or_future_session(generated):
    algo=generated['sr_execution'].StockRadarExecution()
    algo._sr_orders_today=[];algo._sr_trades_today=[];algo._sr_entries={}
    algo._sr_execution=generated['sr_config'].EXECUTION;algo._sr_pending=[{'symbol':'sid','signal_date':'2021-01-05'}]
    with pytest.raises(ValueError,match='Same-session/future'):
        algo.open_session('2021-01-05',{'sid':N(open=50.)})


def test_native_tenth_session_moc_boundary_and_no_more_entries(generated):
    algo=generated['sr_execution'].StockRadarExecution();cfg=generated['sr_config']
    algo._sr_entries={'sid':{'quantity':100,'entry_index':0}};algo._sr_fixed_close=True
    algo._sr_day_index={'day9':8,'day10':9};algo._sr_execution=cfg.EXECUTION
    algo._sr_context={};algo._sr_symbols={'sid':'symbol'};algo._sr_pending=[]
    algo._sr_bundle={'max_positions':10};algo.portfolio=N(cash=100,total_portfolio_value=1000)
    calls=[];algo.market_on_close_order=lambda *args,**kwargs:calls.append((args,kwargs))
    algo.open_session('day9',{'sid':N(open=50.)});assert not calls
    algo.open_session('day10',{'sid':N(open=50.)});assert calls[0][0]==('symbol',-100)
    assert algo._sr_context['sid']['reference'] is None
    n=1255;last_entry=n-cfg.EXECUTION['exit']['max_holding_sessions']
    assert (n-1)-last_entry+1==10


def test_typed_raw_history_uses_sid_clock_and_no_fill_forward(generated):
    from radar.research.high_beta.cloud.data import history_frames
    symbol=N(id='SID');bar=N(end_time=datetime(2021,1,4,16),is_fill_forward=False,
                           open=10,high=11,low=9,close=10,volume=100)
    class Slice:
        def contains_key(self,_):return True
        def __getitem__(self,_):return bar
    class History:
        def __getitem__(self,_):return lambda *args,**kwargs:[Slice()]
    a=N(history=History());first=datetime(2021,1,1);end=datetime(2021,1,5,8,30)
    assert history_frames(a,[symbol],first,end)['SID'].date.iloc[0]==pd.Timestamp('2021-01-04')
    bar.is_fill_forward=True
    with pytest.raises(ValueError,match='fill-forward'):history_frames(a,[symbol],first,end)
    bar.is_fill_forward=False;bar.end_time=datetime(2021,1,5,16)
    with pytest.raises(ValueError,match='future'):history_frames(a,[symbol],first,end)


def test_missing_historical_universe_is_not_successful_zero_signal(generated):
    from radar.research.high_beta.cloud.data import population
    a=N(time=datetime(2021,1,5,8,30),history=lambda *args:pd.Series(dtype=object))
    with pytest.raises(ValueError,match='unavailable'):population(a,object(),'2021-01-04')
    with pytest.raises(ValueError,match='clock'):population(a,object(),'2021-01-05')

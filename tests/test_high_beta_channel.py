from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from radar.research.high_beta.channel import Settings,MarketEvidence,analyze,beta,daily_state,rank,candidate,_channel
from radar.research.parallel_channel import _aggregate
from radar.research.sessions import calendar


def data(n=430,beta_value=2.8,volume=12_000_000):
    days=calendar().sessions_in_range('2023-01-03','2025-12-31')[:n]
    t=np.arange(n);r=.008*np.sin(t*.9)+.004*np.cos(t*.4)
    bench=100*np.cumprod(1+r);stock=40*np.cumprod(1+beta_value*r)
    f=pd.DataFrame(dict(date=days,open=stock*.995,high=stock*1.025,low=stock*.975,close=stock,volume=volume))
    spy=pd.DataFrame(dict(date=days,close=bench,feed='sip',adjustment='split'))
    return f,spy,spy.copy()


def proof(**changes):
    return MarketEvidence(**{**dict(scope='current_listing',identity_trusted=True,common_stock=True,
        source='alpaca',feed='sip',adjustment='split',joint_price_volume_adjustment=True),**changes})


def test_beta_is_paired_ols_with_intercept():
    f,spy,_=data();cfg=Settings()
    result=beta(f.set_index('date').close,spy.set_index('date').close,126,105,cfg)
    assert result['value']==pytest.approx(2.8,abs=1e-11)
    assert result['samples']==126 and result['outliers']==0


def test_missing_session_cannot_become_multi_day_return():
    f,spy,_=data();close=f.set_index('date').close.reindex(pd.DatetimeIndex(f.date))
    close.iloc[-5]=np.nan
    result=beta(close,spy.set_index('date').close,126,105,Settings())
    assert result['samples']==124


def test_zero_variance_benchmark_is_not_infinite_beta():
    f,spy,_=data();spy['close']=100.
    assert beta(f.set_index('date').close,spy.set_index('date').close,126,105,Settings())['reason']=='benchmark_zero_variance'


@pytest.mark.parametrize('column,value,reason',[
    ('adjustment','raw','benchmark_basis_incompatible'),
    ('provider','other','benchmark_source_incompatible')])
def test_benchmark_cannot_mix_price_basis_or_provider(column,value,reason):
    f,spy,qqq=data();spy[column]=value
    r=analyze(f,f.date.iloc[-1],spy,qqq,proof())
    assert r['reason_codes']==[reason] and not r['market_qualified']


def test_same_raw_basis_is_supported_without_mixing_split_benchmark():
    f,spy,qqq=data();spy['adjustment']='raw';qqq['adjustment']='raw'
    r=analyze(f,f.date.iloc[-1],spy,qqq,proof(adjustment='raw'))
    assert r['market_qualified'] and r['market']['beta']['spy_126']['value']==pytest.approx(2.8)


def test_beta_minimum_and_extreme_returns_cannot_be_silently_imputed():
    f,spy,_=data();close=f.set_index('date').close.copy();close.iloc[-1]*=10
    result=beta(close,spy.set_index('date').close,126,126,Settings())
    assert result['outliers']==1 and result['value'] is None


@pytest.mark.parametrize('changes,reason',[
    ({'identity_trusted':False},'identity_untrusted'),({'common_stock':False},'instrument_not_common_stock'),
    ({'feed':'iex'},'non_sip_or_incompatible_source'),({'adjustment':'all'},'price_volume_basis_uncertified'),
    ({'joint_price_volume_adjustment':False},'price_volume_basis_uncertified'),
    ({'scope':'historical_verified'},'historical_absolute_liquidity_uncertified')])
def test_no_shape_score_can_bypass_trust_and_basis_gates(changes,reason):
    f,spy,qqq=data();r=analyze(f,f.date.iloc[-1],spy,qqq,proof(**changes))
    assert r['reason_codes']==[reason] and not r['market_qualified'] and r['channel'] is None


@pytest.mark.parametrize('beta_value,volume,reason',[(1.8,12_000_000,'beta_below_minimum'),(2.8,1000,'liquidity_below_minimum')])
def test_market_hard_gates_precede_channel(beta_value,volume,reason):
    f,spy,qqq=data(beta_value=beta_value,volume=volume)
    r=analyze(f,f.date.iloc[-1],spy,qqq,proof())
    assert reason in r['reason_codes'] and r['channel'] is None and not r['qualified']


def test_future_ohlcv_and_benchmark_mutation_cannot_change_t_result():
    f,spy,qqq=data();t=f.date.iloc[-20]
    expected=analyze(f,t,spy,qqq,proof())
    changed=f.copy();changed.loc[changed.date>t,['open','high','low','close','volume']]*=999
    changed_spy=spy.copy();changed_spy.loc[changed_spy.date>t,'close']=.0001
    assert analyze(changed,t,changed_spy,qqq,proof())==expected


def test_joint_future_split_scale_preserves_beta_and_absolute_amount():
    f,spy,qqq=data();t=f.date.iloc[-1];old=analyze(f,t,spy,qqq,proof())
    scaled=f.copy();scaled[['open','high','low','close']]*=2;scaled['volume']/=2
    new=analyze(scaled,t,spy,qqq,proof())
    assert new['market']['adv20_dollar']==pytest.approx(old['market']['adv20_dollar'])
    assert new['market']['beta']==old['market']['beta']
    assert new['qualified']==old['qualified']


@pytest.mark.parametrize('defect',['missing_spy','missing_stock','source_mixed'])
def test_missing_or_mixed_data_explicitly_refused(defect):
    f,spy,qqq=data()
    if defect=='missing_spy':spy=spy.drop(index=len(spy)-5)
    if defect=='missing_stock':f=f.drop(index=len(f)-5)
    if defect=='source_mixed':f['feed']='sip';f.loc[len(f)-3,'feed']='iex'
    r=analyze(f,f.date.iloc[-1],spy,qqq,proof())
    assert not r['market_qualified']
    assert r['reason_codes'][0] in ['missing_spy_benchmark','missing_exchange_sessions','mixed_source_or_basis']


@pytest.mark.parametrize('trend',[-.003,.003])
def test_monotonic_trend_has_no_clear_retested_channel(trend):
    f,_,_=data();c=50*np.exp(trend*np.arange(len(f)))
    f['close']=c;f['open']=c*.995;f['high']=c*1.01;f['low']=c*.99
    r=_channel(_aggregate(f,'W-FRI').tail(26).reset_index(drop=True),'weekly',Settings())
    assert not r['eligible'] and r['full_swing_count']==0


def test_one_green_candle_during_fast_decline_is_not_reversal():
    f,_,_=data(205);c=np.linspace(60,42,30)
    f.loc[f.index[-30:],'close']=c;f.loc[f.index[-30:],'open']=c*1.01
    f.loc[f.index[-30:],'high']=c*1.02;f.loc[f.index[-30:],'low']=c*.98
    f.loc[f.index[-1],'open']=c[-1]*.99
    r=daily_state(f,40,80,Settings())
    assert r['near_support'] and r['stage']=='stabilization_pending' and not r['stabilizing']


def test_broken_channel_floor_never_gets_near_support_entry_bonus():
    f,_,_=data();f.loc[f.index[-1],['open','high','low','close']]=[34,35,32,33]
    r=daily_state(f,40,80,Settings())
    assert r['stage']=='breakdown' and not r['near_support']


def test_secondary_log_position_waits_even_with_improvement():
    f,_,_=data();f.loc[f.index[-1],'close']=40*2**.4
    r=daily_state(f,40,80,Settings())
    assert r['channel_position']==pytest.approx(.4) and r['secondary_watch'] and not r['near_support']


def test_serial_parallel_same_input_is_exact_and_rejections_never_rank():
    f,spy,qqq=data();t=f.date.iloc[-1]
    def compute(_):return analyze(f,t,spy,qqq,proof())
    serial=[compute(i) for i in range(3)]
    with ThreadPoolExecutor(max_workers=3) as pool:parallel=list(pool.map(compute,range(3)))
    assert serial==parallel
    rejected=candidate({**serial[0],'qualified':False,'watch':False},security_id='unit',symbol='AAA')
    assert rank([rejected])==[]


def test_new_subpackage_does_not_enter_old_freeze_source_glob():
    from pathlib import Path
    import json
    from radar.research.quant_lean import freeze,verify_freeze
    root=Path(__file__).resolve().parents[1]
    # No need to invoke the engine or alter the receipt to prove compatibility.
    old=json.loads((root/'data/research/quant-research-v1/freeze.json').read_text()) if (root/'data/research/quant-research-v1/freeze.json').exists() else None
    if old is not None:verify_freeze(root,old)
    sources={p.name for p in (root/'src/radar/research').glob('*.py')}
    assert not any(name.startswith('high_beta') for name in sources)


def test_current_unknown_or_multi_class_listing_is_not_promoted(tmp_path):
    from radar.research.high_beta.daily import listing_context
    path=tmp_path/'data';path.mkdir()
    pd.DataFrame([
        dict(symbol='AAA',valid_from='2026-10-01',valid_to='2026-10-07',security_type='common',security_name='Example Inc. Common Stock',eligible=True),
        dict(symbol='BBB',valid_from='2026-10-01',valid_to='2026-10-07',security_type='unknown',security_name='Unknown Inc.',eligible=True),
        dict(symbol='CCC',valid_from='2026-10-01',valid_to='2026-10-07',security_type='common',security_name='Dual Inc. Class A Common Stock',eligible=True),
        dict(symbol='CCC',valid_from='2026-10-01',valid_to='2026-10-07',security_type='common',security_name='Dual Inc. Class B Common Stock',eligible=True)
    ]).to_csv(path/'security-master.csv',index=False)
    result,_=listing_context(tmp_path,{'AAA':'Example Inc.','BBB':'Unknown Inc.','CCC':'Dual Inc.','NEW':'New Inc.'},'2026-10-08')
    assert result=={'AAA':True,'BBB':False,'CCC':False,'NEW':False}


def test_new_snapshot_never_overwrites_baseline_or_exports_all_diagnostics(tmp_path):
    from radar.research.high_beta.daily import save,latest
    old=tmp_path/'data/research/daily-quant';old.mkdir(parents=True);(old/'latest.json').write_bytes(b'old baseline')
    result={'as_of':'2026-10-08','version':'high-beta-liquid-channel-v1.2','candidates':[],
            'diagnostics':[{'symbol':'PRIVATE-DIAGNOSTIC'}]}
    a=save(tmp_path,result);b=save(tmp_path,result)
    assert a==b and (old/'latest.json').read_bytes()==b'old baseline'
    assert 'diagnostics' not in latest(tmp_path)
    with pytest.raises(ValueError):latest(tmp_path,True)

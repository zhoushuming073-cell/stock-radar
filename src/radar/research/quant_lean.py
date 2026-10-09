"""Frozen Q1/Q2 signals -> independent native LEAN -> existing RunStore/UI.

Historical membership comes solely from frozen shape research. The optional
exploratory proxy domain is never promoted into the existing formal PIT gate.
Preflight failures block the entire method run, never drop difficult candidates.
"""
from dataclasses import asdict
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
from uuid import uuid4
import duckdb
import pandas as pd
import yaml
from radar.backtest.costs import load_fee_config
from radar.lab.parameters import execution_defaults_from_legacy
from radar.lean.export import prepare_bundle
from radar.lean.runtime import installation,invoke,digest
from radar.lean.result_adapter import normalize
from radar.research.candidates import configurations,fingerprint,code_hash
from radar.research.infrastructure import ResearchInfrastructure
from radar.research.sessions import calendar
from radar.research.historical_quant import scan_historical

def execution_config(cfg):
    r=execution_defaults_from_legacy({'initial_capital':cfg['initial_capital'],'max_new_candidates':10,
       'take_profit':None,'stop_loss':None,'max_holding_sessions':10,'entry_gap_min':-.1,'entry_gap_max':.05,
       'max_position_fraction':1,'minimum_position_fraction':0,'max_order_to_avg_dollar_volume':.02,
       'allocator':'equal_cash','market_guard':'none'},slippage_bps=cfg['slippage_bps'],execution_timing='next_open')
    r['entry_gap']['enabled']=False
    r['exit']['timing']='fixed_horizon_close';r['sizing']['cash_allocation']='equal_remaining_slots'
    return r

def freeze(root,directory):
    root=Path(root);directory=Path(directory);directory.mkdir(parents=True,exist_ok=True)
    cfg=yaml.safe_load((root/'config/quant_research_v1.yaml').read_text())
    a,b=configurations(root);_,identity=installation(root)
    sources=sorted([*root.joinpath('src/radar/research').glob('*.py'),
                    *root.joinpath('src/radar/lean').glob('*.py'),
                    root/'config/quant_vision_labeling_v1.yaml',root/'config/parallel_channel_v1.yaml',
                    root/'config/quant_research_v1.yaml',root/'config/research.yaml'])
    receipt={'version':'q1-q2-freeze-v1','recorded_at':datetime.now(timezone.utc).isoformat(),
             'git_revision':subprocess.check_output(['git','rev-parse','HEAD'],cwd=root,text=True).strip(),
             'source_files':{str(p.relative_to(root)).replace('\\','/'):digest(p) for p in sources},
             'q1':{'version':'fuzzy-shape-v1','config_hash':fingerprint(a['scores']),'scores':a['scores']},
             'q2':{'version':'parallel-channel-v1.1','config_hash':fingerprint(b.__dict__),'settings':asdict(b)},
             'research_config':cfg,'execution':execution_config(cfg),
             'fees':asdict(load_fee_config(root/'config/research.yaml')),'engine_identity':identity,
             'universe_contract':json.loads((root/'config/research_infrastructure_v1.json').read_text())['semantic_hash'],
             'ranking':'qualified only; per-method score descending; stable security_id tie break; top10',
             'duplicate_policy':'no overlapping same security; no hidden candidate substitutions based on Y',
             'source_domain':'bounded frozen Shape Research; vendor daily open-close proxy simulation; NOT certified raw PIT fills',
             'formal_pit':'UNCHANGED_BLOCKED','Fresh':'NOT_RUN','HistoricalTest':'NOT_RUN',
             'no_return_tuning':True}
    path=directory/'freeze.json'
    if path.exists():
        prior=json.loads(path.read_text())
        for key in receipt:
            if key not in {'recorded_at','git_revision'} and prior[key]!=receipt[key]:
                raise ValueError('Frozen study changed: '+key)
        return prior
    path.write_text(json.dumps(receipt,indent=2,allow_nan=False),encoding='utf-8')
    return receipt

def verify_freeze(root,receipt):
    for path,sha in receipt['source_files'].items():
        if digest(Path(root)/path)!=sha:raise ValueError('Frozen code/config changed: '+path)

def execution_inputs(root,rows,window):
    """Whole-run fail closed on incomplete, unsafe or inconsistent fill dependencies."""
    start,end,evaluation_end=window
    sessions=calendar().sessions_in_range(start,evaluation_end)
    days=[str(d.date()) for d in sessions]
    selected=[r for r in rows if r['selected']]
    prices=[];signals=[];mapping={};failures=[]
    by_sid={}
    for r in selected:by_sid.setdefault(r['security_id'],[]).append(r)
    with ResearchInfrastructure(root) as api:
        c=api.core.connection
        for sid,items in sorted(by_sid.items()):
            series={r['provenance']['series_id'] for r in items}
            if len(series)!=1:
                failures.append({'security_id':sid,'reason':'execution_source_switch'});continue
            source=next(iter(series));alias='Q'+hashlib.sha256(sid.encode()).hexdigest()[:12].upper()
            first=items[0];mapping[alias]={'security_id':sid,'symbol':first['symbol'],'source':first['provenance']['source'],'basis':first['provenance']['basis']}
            frame=c.execute("""select * from shape_price where series_id=? and date between ? and ? order by date""",
                            [source,start,evaluation_end]).df()
            required=set()
            for r in items:
                i=days.index(r['decision_date']);required.update(days[i+1:i+11])
            f=frame.loc[frame.date.astype(str).isin(required)].copy()
            if set(f.date.astype(str))!=required:
                failures.append({'security_id':sid,'reason':'missing_10session_fill_prices','missing':len(required-set(f.date.astype(str)))});continue
            if not f.shape_research_ready.all() or f.identity_conflict.any() or f.class_or_name_boundary.any():
                failures.append({'security_id':sid,'reason':'unsafe_identity_or_fill_prices'});continue
            if f[['basis','source','series_id']].drop_duplicates().shape[0]!=1:
                failures.append({'security_id':sid,'reason':'mixed_execution_basis'});continue
            actions=c.execute('select date,factor from split_action where security_id=? and date between ? and ?',
                              [sid,start,evaluation_end]).fetchall()
            if first['provenance']['basis']=='raw' and actions:
                failures.append({'security_id':sid,'reason':'raw_action_requires_existing_certified_native_PIT_contract'});continue
            # Split vendor series are explicit adjusted-unit price-only proxies.
            # No dividend/terminal entitlement or true share-count claim is made.
            for r in items:
                day=r['decision_date']
                bar=frame.loc[frame.date==pd.Timestamp(day)]
                if len(bar)!=1:
                    failures.append({'security_id':sid,'reason':'missing_signal_reference'});continue
                before=frame.loc[frame.date<=pd.Timestamp(day)].tail(20)
                # ADV comes from an additional <=T read, not from forward prices.
                before=c.execute("""select close,volume from shape_price where series_id=? and date<=?
                    order by date desc limit 20""",[source,day]).df()
                if len(before)!=20:failures.append({'security_id':sid,'reason':'missing_causal_adv'});continue
                signals.append(dict(signal_date=day,symbol=alias,rank=r['rank'],strategy_score=r['score'],
                    strategy_id=r['method'],strategy_version=r['version'],reference_close=float(bar.close.iloc[0]),
                    avg_dollar_volume_20=float((before.close*before.volume).mean()),allocation_weight=1))
            p=f[['date','open','high','low','close','volume']].copy();p['symbol']=alias;prices.append(p)
    with duckdb.connect(str(Path(root)/'data/market.duckdb'),read_only=True) as c:
        spy=c.execute("""select date,symbol,open,high,low,close,volume from daily_bars where symbol='SPY'
                         and date between ? and ? order by date""",[start,evaluation_end]).df()
    if list(spy.date.astype(str))!=days:failures.append({'reason':'incomplete_benchmark'})
    if failures:return {'status':'BLOCKED','failures':failures,'selected_signals':len(selected)},None,None,None,mapping
    return {'status':'READY_EXPLORATORY_PROXY_ONLY','selected_signals':len(selected),
            'limitations':['No formal raw PIT execution certification','Homogeneous vendor adjustment units; absolute shares/fees may carry adjustment bias',
                           'Price-only, no dividend or unknown corporate/terminal entitlement; not live-ready']},sessions,signals,(
                 pd.concat([*prices,spy],ignore_index=True) if prices else spy),mapping

def publish_result(root,result,metrics,metadata):
    from radar.lab.store import RunStore
    store=RunStore(Path(root)/'data/strategy-lab/runs.sqlite3')
    run=store.create_run(metadata);store.start_run(run,os.getpid());store.finish_run(run,result,metrics)
    return run

def run_method(root,receipt,directory,split,method):
    verify_freeze(root,receipt);directory=Path(directory)
    audit=json.loads((directory/split/'audit.json').read_text())
    rows=[json.loads(x) for x in (directory/split/'candidates.jsonl').read_text().splitlines()]
    rows=[r for r in rows if r['method']==('q1_fuzzy_shape' if method=='q1' else 'q2_parallel_channel')]
    window=receipt['research_config']['intervals'][split]
    inputs=execution_inputs(root,rows,window);gate=inputs[0]
    gate_path=directory/split/(method+'-execution-gate.json')
    gate_path.write_text(json.dumps(gate,indent=2),encoding='utf-8')
    if gate['status']=='BLOCKED':return gate
    _,sessions,signals,prices,mapping=inputs
    home,identity=installation(Path(root));execution=receipt['execution']
    selected_count=sum(r['selected'] for r in rows)
    run_id=str(uuid4());output=directory/split/(method+'-'+run_id)
    cfg=receipt['research_config'];version=receipt[method]['version']
    metadata=dict(strategy_id=('q1_fuzzy_shape' if method=='q1' else 'q2_parallel_channel'),
                  strategy_version=version,strategy_name=method.upper()+' frozen Quant pilot',
                  engine='lean',engine_identity=identity,engine_code_hash=digest(Path(root)/'src/radar/lean/algorithm.py'),
                  universe_mode='shape_research_v1',quality_tier='bounded-shape-exploratory',
                  window=window,split=split,start_date=window[0],end_date=window[1],evaluation_end=window[2],
                  signal_source='frozen ResearchInfrastructure v1 Q1/Q2 candidate snapshots',
                  data_snapshot=receipt['universe_contract'],source_watermark=window[2],
                  plugin_interface_version='frozen-signals-v1',strategy_path='radar.research.'+method,
                  strategy_code_hash=receipt['source_files']['src/radar/research/fuzzy_shape.py' if method=='q1' else 'src/radar/research/parallel_channel.py'],
                  feature_version=version,config=receipt[method],config_hash=receipt[method]['config_hash'],
                  git_revision=receipt['git_revision'],fee_profile=receipt['fees']['profile'],slippage_bps=cfg['slippage_bps'],
                  execution_policy='T close signal -> T+1 open; tenth trading-session native MOC; equal remaining cash slots',
                  backtest_config_hash=fingerprint(execution),research_config_hash=fingerprint(cfg),
                  resolved_execution=execution,selector_freeze=fingerprint(receipt),execution_preflight=gate,
                  private_security_mapping=mapping,price_proxy_limitations=gate['limitations'])
    manifest=prepare_bundle(home,output,metadata,list(sessions),signals,prices,execution,
                            load_fee_config(Path(root)/'config/research.yaml'),max_positions=10)
    raw=invoke(Path(root),output,manifest,run_id,lambda r:None,lambda:False,expected_identity=identity)
    result,metrics=normalize(output,raw,identity)
    for collection in ['trades','orders','open_positions']:
        for r in result[collection]:
            if r['symbol'] in mapping:r.update(mapping[r['symbol']])
    for point in result['equity']:
        for r in point['positions']:
            if r['symbol'] in mapping:r.update(mapping[r['symbol']])
    trades=result['trades']
    if any(t['holding_sessions']!=10 or t['exit_reason']!='fixed_horizon_close' for t in trades):
        raise ValueError('Primary fixed horizon violated')
    if result['open_positions']:raise ValueError('Primary horizon did not fully settle')
    extra={'mean_holding_sessions':sum(t['holding_sessions'] for t in trades)/len(trades) if trades else None,
           'mean_trade_return':float(pd.Series([t['net_return'] for t in trades]).mean()) if trades else None,
           'median_trade_return':float(pd.Series([t['net_return'] for t in trades]).median()) if trades else None,
           'selected_signals':selected_count,'gross_closed_pnl':sum(t['gross_pnl'] for t in trades),
           'slippage_cost':sum(t['slippage_cost'] for t in trades),
           'selector_daily_counts':[s[method] for s in audit['sessions']],
           'eligible_security_days':audit['eligible_security_days'],'native_result_sha256':digest(raw)}
    result['quant_research_diagnostics']=extra
    store_id=publish_result(root,result,metrics,metadata)
    summary={'status':'PASS_EXPLORATORY_PROXY_ONLY','run_id':store_id,'native_id':run_id,'method':method,
             'split':split,'window':window,'metrics':metrics,'diagnostics':extra,'execution_gate':gate,
             'formal_pit':'BLOCKED_UNCHANGED','path':str(output)}
    (directory/split/(method+'-result-summary.json')).write_text(json.dumps(summary,indent=2,allow_nan=False),encoding='utf-8')
    verify_freeze(root,receipt)
    return summary


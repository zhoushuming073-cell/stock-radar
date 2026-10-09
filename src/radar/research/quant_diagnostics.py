"""Post-selection analytics. Never imported by candidate feature/selection code.

Outcomes are derived only after immutable candidates exist. They are research
diagnostics, not Human Ground Truth and not features for Q1/Q2 selection.
"""
from collections import Counter
import json
import math
from pathlib import Path
import duckdb
import numpy as np
import pandas as pd
from radar.lab.scanner import build_labels,candidate_metrics,evaluation_settings
from radar.research.infrastructure import ResearchInfrastructure
from radar.research.sessions import calendar


def portfolio_diagnostics(result,initial):
    trades=result['trades']; values=pd.Series([t['net_return'] for t in trades],dtype=float)
    daily=pd.Series([initial,*[p['equity'] for p in result['equity']]],dtype=float).pct_change().dropna()
    fees=sum(t['entry_fee']+t['exit_fee'] for t in trades)
    slip=sum(t['slippage_cost'] for t in trades)
    pnl=result['equity'][-1]['equity']-initial
    return {'diagnostic_source':'presentation analytics of reconciled native LEAN fills and equity',
        'annualized_daily_volatility':float(daily.std(ddof=1)*math.sqrt(252)) if len(daily)>1 else None,
        'trade_return_distribution':{str(k):float(v) for k,v in values.quantile([0,.1,.25,.5,.75,.9,1]).items()} if len(values) else {},
        'worst_trade_return':float(values.min()) if len(values) else None,
        'best_trade_return':float(values.max()) if len(values) else None,
        'actual_sizing_cost_attribution':{'net_pnl':pnl,'fees':fees,'slippage':slip,
            'reference_price_pnl_addback':pnl+fees+slip,
            'reference_price_return_addback':(pnl+fees+slip)/initial,
            'scope':'Cost addback at actual native quantities; NOT a counterfactual no-cost portfolio'},
        'exit_years':dict(Counter(str(t['exit_date'])[:4] for t in trades))}


def candidate_diagnostics(root,split_dir,window):
    """Same-T frozen eligible background; unsafe/missing forward paths censored.

    Data is a bounded Shape Research vendor price proxy. Unknown entitlement,
    dividend and issuer continuity risks remain; no formal raw-PIT claim.
    """
    root=Path(root);split_dir=Path(split_dir)
    if not (split_dir/'audit.json').exists():raise ValueError('Frozen candidate audit required before reading outcomes')
    candidates=[json.loads(x) for x in (split_dir/'candidates.jsonl').read_text().splitlines()]
    qualified=pd.DataFrame([r for r in candidates if r['status']=='qualified'])
    start,end,evaluation_end=window;sessions=calendar().sessions_in_range(start,evaluation_end)
    days=[str(d.date()) for d in sessions];positions={d:i for i,d in enumerate(days)}
    settings=evaluation_settings({'event_cooldown_sessions':10})
    with ResearchInfrastructure(root) as api:
        c=api.core.connection
        eligible=c.execute("""select security_id,decision_date,series_id,basis from universe_window_index
            where decision_date between ? and ? and length=126 and supported_membership
            qualify row_number() over(partition by security_id,decision_date order by priority,series_id)=1
            order by decision_date,security_id""",[start,end]).df()
        c.register('diagnostic_series',pd.DataFrame({'series_id':sorted(eligible.series_id.unique())}))
        bars=c.execute("""select p.date,p.series_id as symbol,p.open,p.high,p.low,
            p.shape_research_ready,p.identity_conflict,p.class_or_name_boundary
            from shape_price p join diagnostic_series s on p.series_id=s.series_id
            where p.date between ? and ? order by p.series_id,p.date""",[start,evaluation_end]).df()
        unsafe=~bars.shape_research_ready|bars.identity_conflict|bars.class_or_name_boundary
        bars.loc[unsafe,['open','high','low']]=np.nan
        actions=c.execute('select security_id,date from split_action where date between ? and ?',
                          [start,evaluation_end]).df()
    signal=eligible.rename(columns={'decision_date':'signal_date','series_id':'symbol'}).copy()
    labels=build_labels(signal,bars,sessions,settings)
    action_days={sid:{str(d.date()) for d in group.date} for sid,group in actions.groupby('security_id')}
    for i,r in enumerate(signal.itertuples(index=False)):
        p=positions[str(r.signal_date.date())]
        if r.basis=='raw' and action_days.get(r.security_id,set())&set(days[p+1:p+11]):
            labels.at[i,'label']=None;labels.at[i,'label_status']='censored';labels.at[i,'label_reason']='raw_split_crosses_outcome_horizon'
    background=pd.concat([signal.reset_index(drop=True),labels],axis=1)
    background['day']=background.signal_date.dt.strftime('%Y-%m-%d')
    lookup={(r.security_id,r.day,r.symbol):(r.label,r.label_status,r.label_reason)
            for r in background.itertuples(index=False)}
    with duckdb.connect(str(root/'data/market.duckdb'),read_only=True) as c:
        spy=c.execute("select date,close from daily_bars where symbol='SPY' and date<=? order by date",[end]).df()
    spy['ma200']=spy.close.rolling(200,min_periods=200).mean()
    regime={str(r.date.date()):('unknown' if pd.isna(r.ma200) else 'above_200ma' if r.close>=r.ma200 else 'below_200ma') for r in spy.itertuples(index=False)}
    background['year']=background.day.str[:4];background['regime']=background.day.map(regime).fillna('unknown')
    output={'version':'quant-candidate-diagnostics-v1','evaluation':settings,
        'scope':'Post-selection vendor price proxy diagnostics, NOT Human labels; target-touch 5% within 10 sessions; no candidate refill',
        'background_rows':len(background),'background_exclusions':background.label_reason.value_counts().to_dict(),
        'background_identity':'same decision-day frozen supported 126-session universe, including later disappeared securities where supported',
        'methods':{}}
    for method in ['q1_fuzzy_shape','q2_parallel_channel']:
        subset=qualified.loc[qualified.method==method].copy() if len(qualified) else pd.DataFrame()
        rows=[]
        for r in subset.to_dict('records'):
            key=(r['security_id'],r['decision_date'],r['provenance']['series_id'])
            label,status,reason=lookup.get(key,(None,'censored','missing_frozen_background'))
            rows.append({'security_id':r['security_id'],'symbol':r['symbol'],'signal_date':pd.Timestamp(r['decision_date']),
                'rank':r['rank'],'label':label,'label_status':status,'label_reason':reason,
                'year':r['decision_date'][:4],'regime':regime.get(r['decision_date'],'unknown')})
        frame=pd.DataFrame(rows,columns=['security_id','symbol','signal_date','rank','label','label_status','label_reason','year','regime'])
        metrics=candidate_metrics(frame,background,settings,sessions)
        slices={}
        for dimension in ['year','regime']:
            slices[dimension]={value:candidate_metrics(group,background.loc[background[dimension]==value],settings,sessions)
                for value,group in frame.groupby(dimension)}
        output['methods'][method]={'metrics':metrics,'slices':slices,'censored_reasons':frame.label_reason.value_counts().to_dict()}
        # Private detailed labels cannot be mistaken for user H or leak into a public report.
        if len(frame):frame.assign(label=frame.label.map(lambda x:json.dumps(x,allow_nan=False))).to_parquet(split_dir/(method+'-diagnostic-labels.parquet'),index=False)
    (split_dir/'candidate-diagnostics.json').write_text(json.dumps(output,indent=2,allow_nan=False),encoding='utf-8')
    return output

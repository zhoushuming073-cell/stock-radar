"""Read-only historical adapters over frozen Research Infrastructure v1.

The 126-session universe gate remains authoritative. Q2 additionally requires a
continuous, safe homogeneous long prefix; no current ticker-list fallback.
"""
from collections import Counter
import json
from pathlib import Path
import numpy as np
import pandas as pd
from radar.research.candidates import configurations,q1,q2,rank_candidates,fingerprint,code_hash
from radar.research.infrastructure import ResearchInfrastructure
from radar.pit.shape import normalize_window,canonical_hash
from radar.research.sessions import calendar,require_session

COLUMNS=['date','open','high','low','close','volume']
MEMBERS=('confirmed_member','probable_member')

def long_prefix(rows,decision,length=430):
    x=rows.loc[pd.to_datetime(rows.date)<=pd.Timestamp(decision)].tail(length).copy()
    if x.empty or str(pd.Timestamp(x.date.iloc[-1]).date())!=str(decision):raise ValueError('missing_decision')
    if not x.shape_research_ready.all():raise ValueError('unsafe_long_prefix')
    if not x.membership_status.isin(MEMBERS).all():raise ValueError('unknown_long_prefix')
    if x[['source','basis','series_id']].drop_duplicates().shape[0]!=1:raise ValueError('mixed_long_source_basis')
    dates=calendar().sessions_in_range(x.date.iloc[0],decision)
    if list(pd.to_datetime(x.date))!=list(dates):raise ValueError('incomplete_long_prefix')
    return x

def scan_historical(root,split,start,end,output,progress=None):
    if split not in {'train','validation'}:raise ValueError('only Train/Validation authorized in this task')
    root=Path(root);output=Path(output)
    if not output.resolve().is_relative_to((root/'data').resolve()):raise ValueError('private historical output required')
    cfg1,cfg2=configurations(root);day0=require_session(start);day1=require_session(end)
    if day1<day0:raise ValueError('reversed interval')
    with ResearchInfrastructure(root) as api:
        bounds=api.profile['semantics']['frozen_splits'][split]
        if not bounds[0]<=day0<=day1<=bounds[1]:raise ValueError('interval crosses frozen split')
        c=api.core.connection;contract=api.fingerprint
        idx=c.execute("""select * from universe_window_index where decision_date between ? and ?
          and length=126 and supported_membership
          qualify row_number() over(partition by security_id,decision_date order by priority,series_id)=1
          order by decision_date,security_id""",[day0,day1]).df()
        # Read only the selected frozen series, with prefix warmup. Future prices
        # are not loaded by selection; execution/outcomes are a separate later step.
        c.register('quant_series',pd.DataFrame({'series_id':sorted(idx.series_id.unique())}))
        earliest=calendar().sessions[calendar().sessions.get_indexer([pd.Timestamp(day0)])[0]-430]
        bars=c.execute("""select p.* from shape_price p join quant_series s using(series_id)
          where date between ? and ? order by p.series_id,p.date""",[earliest.date(),day1]).df()
        actions={s:g[['date','factor']].to_dict('records') for s,g in c.execute(
            'select security_id,date,factor from split_action where date<=? order by date',[day1]).df().groupby('security_id')}
        populations=c.execute("""select date,membership_status,count(distinct security_id) n from population
          where date between ? and ? and eligible group by all order by date,membership_status""",[day0,day1]).df()
        groups={s:g for s,g in bars.groupby('series_id',sort=False)}
        result=[];audits=[];distributions={'q1':[],'q2':[]}
        for count,day in enumerate(calendar().sessions_in_range(day0,day1),1):
            stamp=str(day.date());eligible=idx.loc[idx.decision_date==day]
            scores={'q1':[],'q2':[]};exclusions={'q1':Counter(),'q2':Counter()}
            for r in eligible.itertuples(index=False):
                if r.membership_status not in MEMBERS:raise ValueError('untrusted identity membership crossed frozen gate')
                raw=groups[r.series_id]
                prefix=raw.loc[(raw.date>=r.window_start)&(raw.date<=day)].copy()
                if len(prefix)!=126 or not prefix.shape_research_ready.all():raise ValueError('frozen index unsafe')
                normalization_actions=[a for a in actions.get(r.security_id,[]) if pd.Timestamp(a['date'])<=day]
                f=normalize_window(prefix,day,normalization_actions)
                flags=['BOUNDED_SHAPE_RESEARCH_NOT_FORMAL_PIT_EXECUTION']
                if (prefix.shape_research_status!='READY').any():flags.append('MINOR_UNCERTAINTY')
                if not r.security_id.startswith('SEC-'):flags.append('ISSUER_ALIAS_UNKNOWN')
                provenance={'domain':'frozen_shape_research_v1','data_contract':contract,
                            'series_id':r.series_id,'source':r.source,'basis':r.basis,
                            'window_hash':canonical_hash(prefix),'code_hash':code_hash_cached}
                one=q1(f,stamp,cfg1,security_id=r.security_id,symbol=r.historical_ticker,
                       provenance={**provenance,'config_hash':fingerprint(cfg1['scores'])},quality_flags=flags)
                distributions['q1'].append(one.score)
                if one.status!='rejected':scores['q1'].append(one)
                else:exclusions['q1'][one.reason_codes[0]]+=1
                try:
                    long=long_prefix(raw,stamp);lf=normalize_window(long,day,normalization_actions)
                    two=q2(lf,stamp,cfg2,security_id=r.security_id,symbol=r.historical_ticker,
                           provenance={**provenance,'window_hash':canonical_hash(long),'config_hash':fingerprint(cfg2.__dict__)},
                           quality_flags=flags,historical=True)
                    distributions['q2'].append(two.score)
                    if two.status!='rejected':scores['q2'].append(two)
                    else:exclusions['q2'][two.reason_codes[0]]+=1
                except ValueError as e:exclusions['q2'][str(e)]+=1
            overlap=set()
            day_audit={'date':stamp,'eligible_security_days':len(eligible),
                       'exclusions':{k:dict(v) for k,v in exclusions.items()}}
            for key in scores:
                ordered=rank_candidates(scores[key]);selected=[r for r in ordered if r.status=='qualified'][:10]
                selected_ids={r.security_id for r in selected}
                if key=='q1':overlap=selected_ids
                else:overlap=overlap&selected_ids
                day_audit[key]={'counts':dict(Counter(r.status for r in ordered)),'top10':len(selected)}
                for candidate in ordered:
                    item=candidate.model_dump(mode='json');item['split']=split;item['selected']=candidate in selected
                    result.append(item)
            day_audit['selection_overlap']=len(overlap);audits.append(day_audit)
            if progress:progress(f'{split} {count}: {stamp}; eligible {len(eligible)}; Q1 {day_audit["q1"]}; Q2 {day_audit["q2"]}')
    output.mkdir(parents=True,exist_ok=True)
    encoded=[json.dumps(row,sort_keys=True,separators=(',',':'),allow_nan=False) for row in result]
    path=output/'candidates.jsonl'
    if path.exists():
        if path.read_text(encoding='utf-8')!='\n'.join(encoded)+'\n':raise ValueError('immutable historical candidates differ')
    else:path.write_text('\n'.join(encoded)+'\n',encoding='utf-8')
    pd.DataFrame(result).to_parquet(output/'candidates.parquet',index=False)
    report={'split':split,'start':day0,'end':day1,'data_contract':contract,
            'candidate_snapshot':fingerprint(result),'code_hash':code_hash_cached,
            'eligible_security_days':sum(a['eligible_security_days'] for a in audits),
            'population_by_membership':populations.assign(date=populations.date.astype(str)).to_dict('records'),
            'sessions':audits,'score_distributions':{k:pd.Series(v,dtype=float).describe(
               percentiles=[.1,.25,.5,.75,.9]).to_dict() for k,v in distributions.items()},
            'boundaries':'Bounded contiguous Train/Validation interval; not a full-split census. No current-survivor fallback; unknown excluded. Q2 430-bar warmup requires supported safe homogeneous prefix. No Y read during selection.'}
    (output/'audit.json').write_text(json.dumps(report,indent=2,allow_nan=False),encoding='utf-8')
    return report

# Invocation computes this once; public scan validates against the receipt in caller.
code_hash_cached=code_hash()


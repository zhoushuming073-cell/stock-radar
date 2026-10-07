"""Frozen decision-scope audit, preserving prior evidence and all production data."""
from collections import Counter,defaultdict
from datetime import datetime,timezone
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from radar.pit.builder import digest
from radar.pit.features import file_hash
from radar.pit.run import load_dependency,freeze_file
from radar.pit.research import local_research_readiness
from radar.pit.decision import (competitor_interval,resolved_core,daily_top,top_stability,
                               missingness_envelope,candidate_identity,scoped_readiness)


def dump(path,value):
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,allow_nan=False,default=str),encoding='utf-8')


def main():
    root=Path.cwd();base=root/'data/pit/research-grade';out=root/'data/pit/research-final';out.mkdir(exist_ok=True)
    read=lambda name:json.loads((base/name).read_text(encoding='utf-8'))
    rules=json.loads((root/'config/pit_research_decision_rules.json').read_text(encoding='utf-8'))
    freeze_path=out/'rules-freeze.json'
    locked=[root/'config/pit_research_decision_rules.json',root/'src/radar/pit/decision.py',Path(__file__),
            root/'config/pit_research_grade_rules.json',base/'audit.json',base/'core-universe.json',
            base/'identity-risk.json',base/'material-action-risk.json',base/'accepted-prices.manifest.json',
            base/'split-scan.json',base/'dividend-scan.json',base/'diagnostic-features/pit-research.duckdb',
            base/'raw-source.duckdb',base/'accepted-prices.duckdb']
    locked.extend(base/f'scanner-{p}.json' for p in 'ABC')
    references=[freeze_file(p) for p in locked]
    if freeze_path.exists():
        frozen=json.loads(freeze_path.read_text(encoding='utf-8'))
        if frozen['files']!=references: raise ValueError('decision inputs changed after freeze; new version required')
    else:
        frozen={'policy':rules['policy'],'frozen_at':datetime.now(timezone.utc).isoformat(),
                'before_new_decision_analysis':True,'before_new_native_returns':True,
                'prior_scanner_outcomes_known':True,'files':references,'rules_sha256':digest(rules)}
        dump(freeze_path,frozen)
    print('Decision rules and input bytes frozen',flush=True)
    old_gate=local_research_readiness(root)
    audit=read('audit.json');closure=load_dependency(audit['dependency_reference'])
    core=read('core-universe.json')['days'];days=[d['date'] for d in core]
    calendar=closure['calendar'];ids={r['security_id']:r for r in closure['dependencies']}
    risks={r['security_id']:r for r in read('identity-risk.json')['rows']}
    base_rules=json.loads((root/'config/pit_research_grade_rules.json').read_text())
    db=base/'diagnostic-features/pit-research.duckdb'
    with duckdb.connect(str(db),read_only=True) as c:
        price_rows=c.execute('SELECT security_id,CAST(date AS VARCHAR) AS date,open FROM daily_bars').fetchall()
    mappings=pd.DataFrame([m for r in closure['dependencies'] for m in r['mappings']])
    mappings['valid_from']=pd.to_datetime(mappings.valid_from)
    mappings['valid_to']=pd.to_datetime(mappings.valid_to).fillna(pd.Timestamp('2050-12-31'))
    with duckdb.connect(str(base/'raw-source.duckdb'),read_only=True) as c:
        c.register('calendar',pd.DataFrame({'date':pd.to_datetime(calendar),'session_index':range(len(calendar))}))
        c.register('mapping',mappings)
        rolling=c.execute('''WITH x AS (SELECT m.security_id,CAST(b.date AS DATE) AS date,c.session_index,
            b.close,b.close*b.volume AS dollars FROM daily_bars b JOIN calendar c USING(date)
            JOIN mapping m ON b.symbol=m.symbol AND b.date BETWEEN m.valid_from AND m.valid_to),
            r AS (SELECT *,COUNT(*) OVER h AS history_count,MIN(session_index) OVER h AS first_index,
            COUNT(*) OVER l AS recent_count,AVG(dollars) OVER l AS avg_dollars,MIN(dollars) OVER l AS min_dollars
            FROM x WINDOW h AS (PARTITION BY security_id ORDER BY session_index ROWS BETWEEN 125 PRECEDING AND CURRENT ROW),
            l AS (PARTITION BY security_id ORDER BY session_index RANGE BETWEEN 19 PRECEDING AND CURRENT ROW))
            SELECT * FROM r''').df()
    by_day={str(day.date()):part.set_index('security_id') for day,part in rolling.groupby('date')}
    by_price={(sid,day):float(op) for sid,day,op in price_rows}
    population={d['date']:set(d['security_ids']) for d in closure['population']}
    rank_days=[];queue=defaultdict(lambda: {'dates':[],'categories':Counter()});d_days=[]
    for original in core:
        day=original['date'];prior=original['causal_cutoff'];inputs=by_day[prior]
        # Reconstruct exactly the eligible known ranking, including positions beyond 1000.
        part=inputs.loc[inputs.index.isin(population[day])]
        eligible=part.loc[(part.close>=base_rules['core']['price_floor']) & (part.min_dollars>=5e6)
            & (part.avg_dollars>=20e6) & (part.history_count==126)
            & ((part.session_index-part.first_index)==125)]
        ranking=sorted([(sid,float(r.avg_dollars)) for sid,r in eligible.iterrows()],key=lambda r:(-r[1],r[0]))
        if [sid for sid,_ in ranking[:1000]]!=original['security_ids']:
            raise ValueError('rank reconstruction differs from frozen Core')
        bounds=[]
        for sid in original['unknown_security_ids']:
            row=inputs.loc[sid] if sid in inputs.index else None
            recent=[float(row.avg_dollars)]*20 if row is not None and row.recent_count==20 else []
            identity=risks[sid]['research_identity_pass'] or risks[sid]['strict_verified']
            complete=bool(row is not None and row.history_count==126 and row.session_index-row.first_index==125)
            item=competitor_interval(sid,recent,ranking,history_complete=complete,identity_resolved=identity)
            item['date']=day;item['causal_cutoff']=prior
            if row is not None:
                item.update(observed_recent_sessions=int(row.recent_count),observed_history_sessions=int(row.history_count),
                            prior_close=float(row.close),symbols=ids[sid]['symbols'])
            else: item.update(observed_recent_sessions=0,observed_history_sessions=0,symbols=ids[sid]['symbols'])
            bounds.append(item)
            if item['category']!='core_non_competitor':
                queue[sid]['dates'].append(day);queue[sid]['categories'][item['category']]+=1
        competitors=[i for i in bounds if i['category']!='core_non_competitor' and not i['eligible_proven']]
        cutoff=lambda r:ranking[r-1][1] if len(ranking)>=r else None
        rd={'date':day,'prior_session':prior,'original_unknown':len(bounds),
            'noncompetitive_unknown':sum(i['category']=='core_non_competitor' for i in bounds),
            'effective_core_uncertainty':len(competitors),'confirmed_core_members':max(0,1000-len(competitors)),
            'confirmed_definition':'top 1000-n known members cannot be displaced by n possible competitors; identity/action readiness separate',
            'rank_950_dollar_volume':cutoff(950),'rank_1000_dollar_volume':cutoff(1000),
            'rank_1050_dollar_volume':cutoff(1050),'competitors':bounds,
            'upper_membership_displacement':min(len(competitors),1000)}
        rank_days.append(rd);d_days.append({'date':day,'security_ids':resolved_core(ranking,bounds),
            'new_resolved_members':sum(i['eligible_proven'] for i in bounds),'unresolved_not_inserted':len(competitors)})
    dump(out/'core-rank-stability.json',{'days':rank_days,'missing_volume_upper_bound':None,
         'rules_sha256':digest(rules),'proof':'observed exact 20-session mean only; unobserved volume remains unbounded'})
    dump(out/'universe-d.json',{'days':d_days,'cap':1000,'status':'resolved-only diagnostic; not an uncertainty waiver'})
    queue_rows=[{'security_id':sid,'symbols':ids[sid]['symbols'],**v} for sid,v in queue.items()]
    dump(out/'core-competitor-queue.json',{'rows':queue_rows,'scope':'only unresolved true competitors'})
    scanners={p:read('scanner-'+p+'.json') for p in 'ABC'}
    same=all(d['security_ids']==c['security_ids'] for d,c in zip(d_days,core))
    if not same: raise ValueError('resolved D changed; production Scanner recomputation required before sensitivity')
    # Same exact dated population/feature/contract implies same production scan.
    scanners['D']={**scanners['C'],'profile':'D','equivalent_to':'C','equivalence_proof':'all 235 daily membership lists identical; same immutable inputs and production Scanner contract'}
    dump(out/'scanner-D.json',scanners['D'])
    tops={p:daily_top(s['rows'],days) for p,s in scanners.items()}
    pairs={a+b:top_stability(tops[a],tops[b]) for a,b in [('A','B'),('A','C'),('B','C'),('C','D')]}
    unknown={r['date']:[i['security_id'] for i in r['competitors'] if i['category']!='core_non_competitor' and not i['eligible_proven']] for r in rank_days}
    impact=missingness_envelope(tops['C'],unknown)
    dump(out/'decision-stability.json',{'top3':pairs,'top5':{a+b:top_stability(daily_top(scanners[a]['rows'],days,5),daily_top(scanners[b]['rows'],days,5)) for a,b in [('A','C'),('C','D')]},
         'missingness':impact,'trade_eligibility_limitation':'Top3 is an intent diagnostic; holdings, max_positions and repeat candidates may cause Native to buy lower ranks'})
    candidate_ids={p:{r['security_id'] for r in s['rows']} for p,s in scanners.items()}
    candidate_findings={};scopes={};events=[{**e,'date':e['date'][:10]} for e in read('split-scan.json')['events']]
    anomalies=read('price-anomalies.json')['rows'];an_by=defaultdict(list)
    for a in anomalies:an_by[a['security_id']].append(a)
    for p,s in scanners.items():
        required=defaultdict(set);signal_days=defaultdict(list)
        for row in s['rows']:
            sid=row['security_id'];signal=row['signal_date'];i=calendar.index(signal)
            required[sid].update(calendar[i+1:i+12]);signal_days[sid].append(signal)
        rows=[]
        for sid in sorted(candidate_ids[p]):
            r=ids[sid];risk=risks[sid];obs=audit['identity_decisions'][sid]['observations']
            identity=candidate_identity(r,obs,risk,base_rules)
            missing=sorted(d for d in required[sid] if (sid,d) not in by_price)
            legal=any(m.get('valid_to') and m['valid_to'][:10]<max(required[sid]) for m in r['mappings'])
            matched=[e for e in events if e['symbol'] in r['symbols'] and e['date'] in (required[sid]|set(r['required_sessions']))]
            material=[a for a in an_by[sid] if a['kind']!='extreme_volume' and a['date'] in r['required_sessions']]
            split_verified=bool(matched) and all(any(a['effective_date']==e['date'] and a['event_type'] in {'split','reverse_split'} and a['confidence']=='verified' and a['handling_mode']!='blocked' for a in r['actions']) for e in matched)
            relevant_material=bool(legal or material or (matched and not split_verified))
            rows.append({'security_id':sid,'symbols':r['symbols'],'identity':identity,'source_disagreement':risk['source_price_conflict'],
                'missing_execution_sessions':missing,'required_execution_sessions':len(required[sid]),
                'material_unresolved':relevant_material,'lifecycle_ambiguity':legal,
                'unverified_split_events':[] if split_verified else matched,
                'price_action_anomalies':material,'volume_only_flags':sum(a['kind']=='extreme_volume' for a in an_by[sid]),
                'original_material_risk':risk['material_review_required'],
                'first_signal_date':min(signal_days[sid]),'last_signal_date':max(signal_days[sid])})
        scopes[p]={'candidate_ids':len(rows),'signals':len(s['rows']),
            'identity_unresolved':sum(not r['identity']['pass'] for r in rows),
            'execution_price_gaps':sum(len(r['missing_execution_sessions']) for r in rows),
            'required_execution_prices':sum(r['required_execution_sessions'] for r in rows),
            'material_unresolved':sum(r['material_unresolved'] for r in rows),
            'known_split_terminal_unresolved':sum(bool(r['unverified_split_events']) or r['lifecycle_ambiguity'] for r in rows),
            'source_disagreement_ids':sum(r['source_disagreement'] for r in rows)}
        candidate_findings[p]=rows
    dump(out/'candidate-audit.json',{'scopes':scopes,'profiles':candidate_findings,
        'material_scope':'feature required windows + every possible candidate holding interval; volume spikes alone not proof of material action'})
    selected_c=candidate_ids['C'];relevant=set(selected_c)|set(queue)|{sid for d in core for sid in d['security_ids']}
    irrelevant=[sid for sid in ids if sid not in relevant]
    dump(out/'residual-scope.json',{'core_decision_relevant_ids':len(relevant),'outside_core_decision_scope_ids':len(irrelevant),
         'outside_core_decision_scope':irrelevant,'warning':'Core irrelevance is not Full PIT irrelevance; A candidates remain relevant for A native execution'})
    outcomes={p:{'candidate_count':s['metrics']['candidate_count'],
        'hit_rate':s['metrics'].get('hit_5pct_10d_rate'),'path_success':None,
        'mfe':s['metrics'].get('average_mfe_10'),'mae':s['metrics'].get('average_mae_10'),
        'falling_knife':None} for p,s in scanners.items()}
    for p,s in scanners.items():
        labels=[r['label'] for r in s['rows'] if r['label_status']=='labeled' and r['label']]
        for target,field in [('path_success','up_5pct_before_down_5pct_10d'),('falling_knife','false_falling_knife')]:
            values=[float(l[field]) for l in labels if l.get(field) is not None]
            outcomes[p][target]=float(np.mean(values)) if values else None
    dump(out/'universe-sensitivity.json',{'profiles':outcomes,'top3_pair_summary':{p:{k:v for k,v in r.items() if k!='days'} for p,r in pairs.items()},
         'D_equivalent_C':same,'CD_observed_status':'IDENTICAL','robust_status':'FAIL' if impact['uncertain_days'] else 'PASS',
         'native_metrics':None,'interpretation':'C/D observed equality does not resolve competitors absent from both profiles'})
    cash=read('dividend-exposure.json')
    cscope=scopes['C']
    membership=read('membership-evidence.json')
    findings={'frozen_before_analysis':True,'causal_selection_verified':True,
        'decision_uncertainty_bounded':not impact['uncertain_days'] and cscope['identity_unresolved']==0 and cscope['material_unresolved']==0,
        'membership_crosschecks_verified':(membership['secondary_nasdaq_days']==len(days)
            and not membership['future_listing_anomalies'] and len(population)==len(days)),
        'maximum_daily_true_competitors':max(r['effective_core_uncertainty'] for r in rank_days),
        'top3_slot_overlap':pairs['CD']['slot_overlap'],'identical_top3_days':pairs['CD']['identical_day_fraction'],
        'maximum_unknown_changed_top3_slots':impact['maximum_daily_changed_slots'],
        'outcomes_stable':not impact['uncertain_days'],
        'candidate_identity_unresolved':cscope['identity_unresolved'],
        'candidate_execution_gaps':cscope['execution_price_gaps'],
        'candidate_material_unresolved':cscope['material_unresolved'],
        'known_split_terminal_unresolved':cscope['known_split_terminal_unresolved'],
        'feature_ranking_scope_complete':not impact['uncertain_days'] and not cscope['source_disagreement_ids'],
        'ordinary_dividend_return_bound':cash['portfolio_return_upper_bound'],'native_input_verified':False}
    result=scoped_readiness(findings,rules)
    dump(out/'readiness.json',{'findings':findings,'result':result,'base_strict_and_research_gate_unchanged':old_gate['dependency_sha256'],
         'rules_freeze':freeze_file(freeze_path)})
    if result['ready']: raise ValueError('PASS requires real Native release implementation; never silently stop or fallback')
    print(json.dumps({'core_original_unknown_range':[min(d['original_unknown'] for d in rank_days),max(d['original_unknown'] for d in rank_days)],
        'effective_unknown_range':[min(d['effective_core_uncertainty'] for d in rank_days),max(d['effective_core_uncertainty'] for d in rank_days)],
        'noncompetitive_proof_rows':sum(d['noncompetitive_unknown'] for d in rank_days),
        'candidate_scopes':scopes,'top3':{p:{k:v for k,v in r.items() if k!='days'} for p,r in pairs.items()},'readiness':result},ensure_ascii=False,indent=2),flush=True)


if __name__=='__main__':main()

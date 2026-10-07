"""Second evidence pass: known recent liquidity failures and exact native window."""
from collections import Counter,defaultdict
import json
from pathlib import Path

import duckdb
import pandas as pd

from audit_pit_research_decisions import dump
from finalize_pit_research_evidence import dividend_bound
from radar.pit.run import load_dependency,freeze_file
from radar.pit.features import file_hash
from radar.pit.builder import digest
from radar.pit.decision import missingness_envelope,daily_top,scoped_readiness


def main():
    root=Path.cwd();base=root/'data/pit/research-grade';stage=root/'data/pit/research-final';out=stage/'resolved-scope';out.mkdir(exist_ok=True)
    read=lambda name:json.loads((stage/name).read_text(encoding='utf-8'))
    get=lambda name:json.loads((base/name).read_text(encoding='utf-8'))
    rules=json.loads((root/'config/pit_research_decision_rules.json').read_text())
    old=read('rules-freeze.json')
    # The first immutable policy remains unchanged throughout data resolution.
    if digest(rules)!=old['rules_sha256']:raise ValueError('release thresholds changed')
    frozen=[freeze_file(p) for p in [Path(__file__),stage/'core-rank-stability.json',stage/'candidate-audit.json',
        stage/'decision-stability.json',root/'config/pit_research_decision_rules.json',base/'raw-source.duckdb']]
    freeze=out/'inputs.json'
    if freeze.exists() and json.loads(freeze.read_text())['files']!=frozen:raise ValueError('resolution inputs changed; version required')
    if not freeze.exists():dump(freeze,{'files':frozen,'rules_sha256':digest(rules),'thresholds_unchanged':True})
    closure=load_dependency(get('audit.json')['dependency_reference'])
    rank=read('core-rank-stability.json');ids={r['security_id']:r for r in closure['dependencies']}
    pairs=pd.DataFrame([{'security_id':i['security_id'],'date':d['date'],'prior':d['prior_session'],
        'start':closure['calendar'][closure['calendar'].index(d['prior_session'])-19]} for d in rank['days']
        for i in d['competitors'] if i['category']!='core_non_competitor'])
    for col in ['date','prior','start']:pairs[col]=pd.to_datetime(pairs[col])
    mapping=pd.DataFrame([m for sid in set(pairs.security_id) for m in ids[sid]['mappings']])
    for col in ['valid_from','valid_to']:mapping[col]=pd.to_datetime(mapping[col]).fillna(pd.Timestamp('2050-12-31'))
    with duckdb.connect(str(base/'raw-source.duckdb'),read_only=True) as c:
        c.register('pairs',pairs);c.register('mapping',mapping)
        recent=c.execute('''SELECT p.security_id,CAST(CAST(p.date AS DATE) AS VARCHAR) AS date,COUNT(b.date) AS observed,
            MIN(b.close*b.volume) AS minimum_dollar_volume,SUM(b.close*b.volume)/20 AS liquidity_lower,
            SUM(b.close*b.volume)/COUNT(b.date) AS observed_average,
            MIN(CASE WHEN b.date=p.prior THEN b.close END) AS prior_close
            FROM pairs p LEFT JOIN mapping m ON p.security_id=m.security_id
            LEFT JOIN daily_bars b ON b.symbol=m.symbol AND b.date BETWEEN m.valid_from AND m.valid_to
            AND b.date BETWEEN p.start AND p.prior GROUP BY 1,2''').df()
    recent_by={(r.security_id,r.date):r for r in recent.itertuples()}
    summary=[];remaining=defaultdict(list);proofs=[]
    for d in rank['days']:
        before=d['effective_core_uncertainty'];counts=Counter();noncompetitive=d['noncompetitive_unknown']
        for item in d['competitors']:
            if item['category']=='core_non_competitor':continue
            r=recent_by[(item['security_id'],d['date'])]
            failure=(r.observed>0 and r.minimum_dollar_volume<rules_base_minimum(root))
            if failure:
                noncompetitive+=1;counts['known_recent_daily_liquidity_failure']+=1
                proofs.append({'date':d['date'],'security_id':item['security_id'],'symbols':ids[item['security_id']]['symbols'],
                    'status':'core_non_competitor','proof':'at least one observed session in past 20 violates unchanged daily dollar-volume floor',
                    'minimum_observed_dollar_volume':float(r.minimum_dollar_volume),'observed_sessions':int(r.observed),
                    'not_missingness_exclusion':True})
            else:
                remaining[d['date']].append(item['security_id']);counts[item['category']]+=1
        summary.append({'date':d['date'],'original_unknown':d['original_unknown'],'after_exact_rank_proof':before,
            'effective_core_uncertainty':len(remaining[d['date']]),'noncompetitive_unknown':noncompetitive,
            'confirmed_core_members_lower':max(0,1000-len(remaining[d['date']])),
            'rank_950_dollar_volume':d['rank_950_dollar_volume'],'rank_1000_dollar_volume':d['rank_1000_dollar_volume'],
            'rank_1050_dollar_volume':d['rank_1050_dollar_volume'],'remaining_categories':dict(counts)})
    dump(out/'core-rank-stability.json',{'days':summary,'additional_irrelevance_proofs':proofs,
        'remaining_competitors':dict(remaining),'rule':'same 20-session/$5m daily minimum; absent prior-day bar does not erase other observed failures'})
    native_calendar=[d for d in closure['calendar'] if rules['window'][0]<=d<=rules['window'][2]]
    full_calendar=closure['calendar'];candidate=read('candidate-audit.json');scanners={p:get('scanner-'+p+'.json') for p in 'ABC'}
    scanners['D']=read('scanner-D.json')
    db=base/'diagnostic-features/pit-research.duckdb'
    with duckdb.connect(str(db),read_only=True) as c:
        prices=c.execute('SELECT security_id,CAST(date AS VARCHAR) AS date,open FROM daily_bars').df()
        benchmark=c.execute("SELECT COUNT(*) FROM daily_bars WHERE symbol='SPY' AND date BETWEEN ? AND ?",[rules['window'][0],rules['window'][2]]).fetchone()[0]
    present=set(zip(prices.security_id,prices.date));prices.date=prices.date.astype(str)
    an=get('price-anomalies.json')['rows'];an_by=defaultdict(list)
    for a in an:an_by[a['security_id']].append(a)
    scopes={};audited={};cash_by={};div=get('dividend-scan.json')['events']
    mapped_div=[]
    for e in div:
        day=e['date'][:10]
        matched=[sid for sid,r in ids.items() if any(m['symbol']==e['symbol'] and m['valid_from'][:10]<=day<=(m['valid_to'] or '9999')[:10] for m in r['mappings'])]
        if len(set(matched))==1:mapped_div.append({**e,'date':day,'security_id':matched[0]})
    split=get('split-scan.json')['events']
    for p,s in scanners.items():
        feature=defaultdict(set);execution=defaultdict(set)
        for signal in s['rows']:
            sid=signal['security_id'];i=full_calendar.index(signal['signal_date'])
            feature[sid].update(full_calendar[max(0,i-125):i+1])
            execution[sid].update(d for d in full_calendar[i+1:i+12] if d<=rules['window'][2])
        rows=[]
        for old_row in candidate['profiles'][p]:
            sid=old_row['security_id'];r=ids[sid];relevant=feature[sid]|execution[sid]
            missing=sorted(d for d in execution[sid] if (sid,d) not in present)
            events=[{**e,'date':e['date'][:10]} for e in split if e['symbol'] in r['symbols'] and e['date'][:10] in relevant]
            verified=all(any(a['effective_date']==e['date'] and a['event_type'] in {'split','reverse_split'}
                and a['confidence']=='verified' and a['handling_mode']!='blocked' for a in r['actions']) for e in events)
            price_flags=[a for a in an_by[sid] if a['kind']!='extreme_volume' and a['date'] in relevant]
            # A finite mapping ending before possible last holding is a lifecycle
            # uncertainty, not a confirmed legal delisting or invented payout.
            lifecycle=any(m.get('valid_to') and m['valid_to'][:10]<max(execution[sid])
                and m['valid_to'][:10]>=min(feature[sid]) for m in r['mappings'])
            material=bool(price_flags or lifecycle or not verified)
            rows.append({**old_row,'missing_execution_sessions':missing,'required_execution_sessions':len(execution[sid]),
                'material_unresolved':material,'lifecycle_ambiguity':lifecycle,'unverified_split_events':[] if verified else events,
                'price_action_anomalies':price_flags,'feature_price_missing':sum((sid,d) not in present for d in feature[sid])})
        audited[p]=rows;scopes[p]={'candidate_ids':len(rows),'signals':len(s['rows']),
            'identity_unresolved':sum(not r['identity']['pass'] for r in rows),
            'execution_price_gaps':sum(len(r['missing_execution_sessions']) for r in rows),
            'required_execution_prices':sum(r['required_execution_sessions'] for r in rows),
            'material_unresolved':sum(r['material_unresolved'] for r in rows),
            'split_or_lifecycle_ambiguity_ids':sum(bool(r['unverified_split_events']) or r['lifecycle_ambiguity'] for r in rows),
            'source_disagreement_ids':sum(r['source_disagreement'] for r in rows),
            'candidate_feature_price_gaps':sum(r['feature_price_missing'] for r in rows)}
        cash_by[p]=dividend_bound(s['rows'],native_calendar,prices.to_dict('records'),mapped_div,1/3)
    dump(out/'candidate-audit.json',{'scopes':scopes,'profiles':audited,
        'required_end':rules['window'][2],'no_beyond_evaluation_execution_dependency':True})
    dump(out/'dividend-exposure.json',cash_by)
    impact=missingness_envelope(daily_top(scanners['C']['rows'],list(remaining)),remaining)
    dump(out/'missingness-impact.json',impact)
    old_findings=read('readiness.json')['findings'];cs=scopes['C']
    findings={**old_findings,'maximum_daily_true_competitors':max(r['effective_core_uncertainty'] for r in summary),
        'maximum_unknown_changed_top3_slots':impact['maximum_daily_changed_slots'],
        'outcomes_stable':not impact['uncertain_days'],'candidate_identity_unresolved':cs['identity_unresolved'],
        'candidate_execution_gaps':cs['execution_price_gaps'],'candidate_material_unresolved':cs['material_unresolved'],
        'known_split_terminal_unresolved':cs['split_or_lifecycle_ambiguity_ids'],
        'ordinary_dividend_return_bound':cash_by['C']['portfolio_return_upper_bound'],
        'benchmark_price_complete':benchmark==len(native_calendar),
        'feature_ranking_scope_complete':not impact['uncertain_days'] and cs['candidate_feature_price_gaps']==0 and cs['source_disagreement_ids']==0}
    result=scoped_readiness(findings,rules)
    dump(out/'readiness.json',{'findings':findings,'result':result,'thresholds_unchanged':True,
        'artifacts':[freeze_file(p) for p in out.glob('*.json') if p.name!='readiness.json']})
    queue=Counter(sid for day,sids in remaining.items() for sid in sids)
    dump(out/'priority-queue.json',{'competitors':[{'security_id':sid,'symbols':ids[sid]['symbols'],'decision_days':n} for sid,n in queue.most_common()],
        'candidate_prices':[{'security_id':r['security_id'],'symbols':r['symbols'],'dates':r['missing_execution_sessions']}
            for r in audited['C'] if r['missing_execution_sessions']],
        'candidate_material':[r for r in audited['C'] if r['material_unresolved']],
        'no_full_market_cleanup':True})
    print(json.dumps({'effective_core_uncertainty_range':[min(r['effective_core_uncertainty'] for r in summary),max(r['effective_core_uncertainty'] for r in summary)],
        'additional_known_liquidity_proofs':len(proofs),'distinct_remaining_competitors':len(queue),
        'candidate_scopes':scopes,'C_dividend_possible_events':cash_by['C']['possible_events'],
        'C_cash_yield_budget':cash_by['C']['known_exposure_sum'],'gate':result},indent=2),flush=True)


def rules_base_minimum(root):
    return 5000000.0  # inherited immutable base core rule; never an empirical estimate


if __name__=='__main__':main()

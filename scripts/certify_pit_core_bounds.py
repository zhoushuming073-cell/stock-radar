"""Recheck liquidity exclusions against identity-cleared eligible competitors only."""
from collections import Counter
import json
from pathlib import Path

import duckdb
import pandas as pd

from audit_pit_research_decisions import dump
from radar.pit.features import file_hash
from radar.pit.run import freeze_file, load_dependency
from radar.pit.decision import competitor_interval, daily_top, missingness_envelope, scoped_readiness
from radar.pit.decision_bounds import score_stress


def main():
    root=Path.cwd();stage=root/'data/pit/research-final';base=root/'data/pit/research-grade'
    out=stage/'identity-safe-bounds';out.mkdir(exist_ok=True)
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    inputs=[Path(__file__),stage/'core-rank-stability.json',stage/'focused-resolutions/core-rank-stability.json',
        stage/'focused-resolutions/readiness.json',base/'identity-risk.json',base/'raw-source.duckdb',base/'audit.json',
        stage/'rules-freeze.json',root/'config/pit_research_decision_rules.json',root/'src/radar/pit/decision.py']
    files=[freeze_file(p) for p in inputs];f=out/'inputs.json'
    if f.exists() and read(f)['files']!=files:raise ValueError('identity-safe input version changed')
    if not f.exists():dump(f,{'files':files,'purpose':'do not use unresolved known identities as definitely eligible blockers'})
    rules=read(root/'config/pit_research_decision_rules.json');first=read(stage/'rules-freeze.json')
    for ref in first['files']:
        if file_hash(Path(ref['path']))!=ref['sha256']:raise ValueError('frozen original changed')
    closure=load_dependency(read(base/'audit.json')['dependency_reference']);calendar=closure['calendar']
    risks={r['security_id']:r for r in read(base/'identity-risk.json')['rows']}
    resolved={sid for sid,r in risks.items() if r['research_identity_pass'] or r['strict_verified']}
    mapping=pd.DataFrame([m for r in closure['dependencies'] for m in r['mappings']])
    mapping['valid_from']=pd.to_datetime(mapping.valid_from)
    mapping['valid_to']=pd.to_datetime(mapping.valid_to).fillna(pd.Timestamp('2050-12-31'))
    with duckdb.connect(str(base/'raw-source.duckdb'),read_only=True) as c:
        c.register('calendar',pd.DataFrame({'date':pd.to_datetime(calendar),'session_index':range(len(calendar))}))
        c.register('mapping',mapping)
        rolling=c.execute('''WITH x AS (SELECT m.security_id,CAST(b.date AS DATE) AS date,c.session_index,
            b.close,b.close*b.volume AS dollars FROM daily_bars b JOIN calendar c USING(date)
            JOIN mapping m ON b.symbol=m.symbol AND b.date BETWEEN m.valid_from AND m.valid_to),
            r AS (SELECT *,COUNT(*) OVER h AS history_count,MIN(session_index) OVER h AS first_index,
            COUNT(*) OVER l AS recent_count,AVG(dollars) OVER l AS avg_dollars,MIN(dollars) OVER l AS min_dollars
            FROM x WINDOW h AS (PARTITION BY security_id ORDER BY session_index ROWS BETWEEN 125 PRECEDING AND CURRENT ROW),
            l AS (PARTITION BY security_id ORDER BY session_index RANGE BETWEEN 19 PRECEDING AND CURRENT ROW)) SELECT * FROM r''').df()
    by_day={str(day.date()):part.set_index('security_id') for day,part in rolling.groupby('date')}
    population={p['date']:set(p['security_ids']) for p in closure['population']}
    rank=read(stage/'core-rank-stability.json');focused=read(stage/'focused-resolutions/core-rank-stability.json')
    proof_keys={(r['date'],r['security_id']) for r in focused['additional_irrelevance_proofs']}
    proof_keys.update((r['date'],r['security_id']) for r in read(stage/'resolved-scope/core-rank-stability.json')['additional_irrelevance_proofs'])
    core={d['date']:d['security_ids'] for d in read(base/'core-universe.json')['days']}
    days=[];remaining={};safe_proofs=[];reopened=[]
    for day in rank['days']:
        date=day['date'];prior=day['prior_session'];part=by_day[prior]
        eligible=part.loc[part.index.isin(population[date]&resolved)]
        eligible=eligible.loc[(eligible.close>=5)&(eligible.min_dollars>=5e6)&(eligible.avg_dollars>=20e6)
            &(eligible.history_count==126)&((eligible.session_index-eligible.first_index)==125)]
        ranking=[(sid,float(r.avg_dollars)) for sid,r in eligible.iterrows()]
        kept=[]
        for item in day['competitors']:
            sid=item['security_id']
            if (date,sid) in proof_keys:continue
            proof=competitor_interval(sid,[item['dollar_volume_upper']]*20 if item['dollar_volume_upper'] is not None else [],ranking)
            if proof['category']=='core_non_competitor':safe_proofs.append({'date':date,**proof})
            else:
                kept.append(sid)
                if item['category']=='core_non_competitor':reopened.append({'date':date,'security_id':sid,'original_rank':item['best_rank'],'identity_safe_best_rank':proof['best_rank']})
        remaining[date]=kept;ambiguous=[sid for sid in core[date] if sid not in resolved]
        days.append({'date':date,'original_unknown':day['original_unknown'],'effective_unknown_competitors':len(kept),
            'identity_cleared_price_eligible_count':len(ranking),'known_core_identity_uncertain':len(ambiguous),
            'known_core_identity_uncertain_ids':ambiguous,'noncompetitive_unknown':day['original_unknown']-len(kept),
            'scope_note':'effective_unknown excludes separate known-Core identity/action uncertainty; no unconditional confirmed-members lower bound'})
    dump(out/'core-rank-stability.json',{'days':days,'remaining_competitors':remaining,'identity_safe_rank_proofs':safe_proofs,
        'conditional_rank_exclusions_reopened':reopened,'irrelevance_proofs_from_observed_floor_or_new_class':len(proof_keys),
        'certification_level':'research identity policy, not legal vendor-grade master'})
    scanner=read(base/'scanner-C.json');stress=score_stress(scanner['rows'],remaining,core)
    impact=missingness_envelope(daily_top(scanner['rows'],list(remaining)),remaining)
    dump(out/'score-stress.json',stress);dump(out/'missingness-impact.json',impact)
    findings=read(stage/'focused-resolutions/readiness.json')['findings']
    findings['maximum_daily_true_competitors']=max(d['effective_unknown_competitors'] for d in days)
    gate=scoped_readiness(findings,rules)
    dump(out/'readiness.json',{'findings':findings,'result':gate})
    evidence=read(root/'reports/evidence/pit-research-final-evidence-2026-10-07.json')
    evidence['conditional_liquidity_unknown_range']=evidence['effective_core_uncertainty_range']
    evidence['effective_core_uncertainty_range']=[min(d['effective_unknown_competitors'] for d in days),max(d['effective_unknown_competitors'] for d in days)]
    evidence['known_core_identity_uncertain_range']=[min(d['known_core_identity_uncertain'] for d in days),max(d['known_core_identity_uncertain'] for d in days)]
    evidence['identity_cleared_price_eligible_range']=[min(d['identity_cleared_price_eligible_count'] for d in days),max(d['identity_cleared_price_eligible_count'] for d in days)]
    evidence['identity_safe_rank_proofs']=len(safe_proofs);evidence['reopened_conditional_rank_exclusions']=len(reopened)
    evidence['initial_exact_rank_proofs']=sum(d['noncompetitive_unknown'] for d in rank['days'])
    evidence['remaining_distinct_competitors']=len(set(sid for sids in remaining.values() for sid in sids))
    evidence['confirmed_core_lower_range']=None
    evidence['confirmed_members_note']='939-978 was conditional on all known Core eligibility; unresolved known identities prohibit calling it an unconditional proof'
    evidence['missingness']={k:v for k,v in impact.items() if k!='days'}
    evidence['score_stress']={k:v for k,v in stress.items() if k!='days'};evidence['readiness']=gate
    evidence['artifacts'].extend(freeze_file(p) for p in sorted(out.glob('*.json')))
    dump(root/'reports/evidence/pit-research-final-evidence-2026-10-07.json',evidence)
    print(json.dumps({k:evidence[k] for k in ['effective_core_uncertainty_range','conditional_liquidity_unknown_range',
        'known_core_identity_uncertain_range','identity_cleared_price_eligible_range','identity_safe_rank_proofs','reopened_conditional_rank_exclusions','remaining_distinct_competitors']},indent=2),flush=True)


if __name__=='__main__':main()

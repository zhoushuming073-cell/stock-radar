"""Focused, evidence-bound final audit. Never launches blocked Native or edits old stores."""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import unicodedata

import duckdb
import pandas as pd

from audit_pit_research_decisions import dump
from radar.pit.builder import digest
from radar.pit.features import file_hash
from radar.pit.run import freeze_file, load_dependency
from radar.pit.research import local_research_readiness
from radar.pit.decision import daily_top, missingness_envelope, scoped_readiness
from radar.pit.decision_bounds import short_history_proof, executable_raw_bar, score_stress, holding_mapping_gaps


def main():
    root=Path.cwd(); base=root/'data/pit/research-grade'; stage=root/'data/pit/research-final'
    out=stage/'focused-resolutions'; out.mkdir(exist_ok=True)
    read=lambda p:json.loads(p.read_text(encoding='utf-8'))
    rules=read(root/'config/pit_research_decision_rules.json'); original=read(stage/'rules-freeze.json')
    if digest(rules)!=original['rules_sha256']:raise ValueError('frozen thresholds changed')
    for f in original['files']:
        if file_hash(Path(f['path']))!=f['sha256']:raise ValueError('original input changed: '+f['path'])
    inputs=[Path(__file__),root/'src/radar/pit/decision_bounds.py',stage/'resolved-scope/core-rank-stability.json',
            stage/'resolved-scope/candidate-audit.json',stage/'resolved-scope/readiness.json',
            stage/'universe-d.json',stage/'universe-sensitivity.json',stage/'resolved-scope/dividend-exposure.json']
    inputs.extend(sorted((stage/'target-evidence').glob('*.json')))
    documents=read(stage/'target-evidence/issuer-documents.json')
    inputs.extend(Path(d['path']) for d in documents if d.get('accepted_for_rank_proof'))
    files=[freeze_file(p) for p in inputs]
    freeze=out/'inputs.json'
    if freeze.exists() and read(freeze)['files']!=files:raise ValueError('focused input version changed')
    if not freeze.exists():dump(freeze,{'files':files,'frozen_at':datetime.now(timezone.utc).isoformat(),
        'thresholds_unchanged':True,'rules_sha256':digest(rules),'before_focused_analysis':True})
    print('Focused resolution inputs frozen',flush=True)
    old_gate=local_research_readiness(root)  # physical dependencies remain valid
    audit=read(base/'audit.json'); closure=load_dependency(audit['dependency_reference'])
    ids={r['security_id']:r for r in closure['dependencies']}; calendar=closure['calendar']
    text=lambda name:unicodedata.normalize('NFKC',read(stage/'target-evidence'/name))
    primary=text('primary-web-receipt.json'); focused=text('focused-primary-web.json')
    # Normalized primary-site connector receipts are distinctly labelled, not HTTP 200 payloads.
    assertions=[(primary,'June 14, 2024'),(primary,'July 2, 2024'),(focused,'May 8, 2024'),
        (focused,'June 1, 2023'),(focused,'Class A Common Stock is listed')]
    if not all(term in body for body,term in assertions):raise ValueError('primary document evidence missing')
    facts=[]
    spec=[('TEM','Tempus','2024-06-14','2024-06-14','primary-web-receipt.json'),
          ('LINE','Lineage','2024-07-25','2024-07-25',None),
          ('SW','Smurfit','2024-07-08','2024-07-09',None),
          ('FUN','Six Flags','2024-07-02','2024-07-02','primary-web-receipt.json'),
          ('NNE','Nano Nuclear','2024-05-08','2024-05-08','focused-primary-web.json')]
    for symbol,name,first,available,receipt in spec:
        d=next((d for d in documents if d['symbol']==symbol),{})
        if receipt:
            source=stage/'target-evidence'/receipt; form='normalized primary connector receipt'
        else:
            if not d.get('accepted_for_rank_proof'):raise ValueError('issuer HTTP evidence not accepted')
            source=Path(d['path']); form='publisher HTTP 200 raw payload'
        facts.append({'symbol':symbol,'issuer_name':name,'first_trading':first,'available_on':available,
            'source_sha256':file_hash(source),'source_form':form,'source_url':d.get('url') or
            'https://ir.nanonuclearenergy.com/news-releases/news-release-details/nano-nuclear-energy-announces-pricing-initial-public-offering',
            'scope':'new listed class only; no predecessor continuity assumed'})
    dump(out/'dated-class-facts.json',facts)
    prior=read(stage/'resolved-scope/core-rank-stability.json')
    raw=read(stage/'target-evidence/raw-alpaca-probe.json')
    gh=read(stage/'target-evidence/raw-gh-series.json')
    probe=raw['bars']+gh['bars']; zero=[b for b in probe if b['volume']==0]
    summary=[]; remaining={}; proofs=[]
    for day in prior['days']:
        date=day['date']; retained=[]; count=0
        recent=calendar[max(0,calendar.index(date)-20):calendar.index(date)]
        for sid in prior['remaining_competitors'][date]:
            record=ids[sid]; proof=None
            for fact in facts:
                if fact['symbol'] not in record['symbols']:continue
                proof=short_history_proof(date,fact,calendar,record['mappings'][0]['security_name'])
                if proof:break
            # Observed zero dollar volume breaks the original daily minimum;
            # a zero-volume quote is never installed as an executable bar.
            if not proof:
                for bar in zero:
                    if bar['date'] in recent and any(m['symbol']==bar['symbol'] and m['valid_from'][:10]<=bar['date']<=(m.get('valid_to') or '9999')[:10] for m in record['mappings']):
                        proof={'status':'core_non_competitor','reason':'observed zero-volume recent session violates $5m daily minimum',
                            'observed_session':bar['date'],'source_sha256':file_hash(stage/'target-evidence'/('raw-gh-series.json' if bar['symbol']=='GH' else 'raw-alpaca-probe.json'))}
                        break
            if proof:count+=1;proofs.append({'date':date,'security_id':sid,'symbols':record['symbols'],**proof})
            else:retained.append(sid)
        remaining[date]=retained
        summary.append({**day,'before_focused_resolution':day['effective_core_uncertainty'],
            'effective_core_uncertainty':len(retained),'noncompetitive_unknown':day['noncompetitive_unknown']+count,
            'confirmed_core_members_lower':max(0,1000-len(retained))})
    dump(out/'core-rank-stability.json',{'days':summary,'remaining_competitors':remaining,'additional_irrelevance_proofs':proofs,
        'count_unit':'security/date; intervals denote possible competitors, not confirmed omissions',
        'TLN':'Nasdaq uplisting does not prove a new class: OTC TLNE predecessor remains unresolved',
        'GH':'zero-volume mark proves daily liquidity failure only, not 126 traded sessions or a D insertion'})
    candidates=read(stage/'resolved-scope/candidate-audit.json'); scanners={p:read(base/f'scanner-{p}.json') for p in 'ABC'}
    scanners['D']=read(stage/'scanner-D.json')
    smr='OBS-6d97c9e6e818f434d3ac79a7'; smr_row=next(r for r in candidates['profiles']['C'] if r['security_id']==smr)
    expected=smr_row['missing_execution_sessions']
    episodes=[r for r in ids.values() if 'SMR' in r['symbols']]
    names={m['security_name'] for r in episodes for m in r['mappings']}
    cik={o['cik'].lstrip('0') for r in episodes for o in audit['identity_decisions'][r['security_id']]['observations'] if o.get('cik')}
    pre=[o for o in audit['identity_decisions'][smr]['observations'] if o['available_on']<=smr_row['first_signal_date']]
    if names!={'NuScale Power Corporation Class A Common Stock'} or cik!={'1822966'} or len(pre)<2:
        raise ValueError('SMR class/issuer evidence failed; ticker-only merge forbidden')
    alpaca={b['date']:b for b in raw['bars'] if b['symbol']=='SMR'}
    with duckdb.connect(str(base/'raw-source.duckdb'),read_only=True) as conn:
        dolt={str(r['date'])[:10]:r for r in conn.execute("SELECT * FROM daily_bars WHERE symbol='SMR' AND date BETWEEN '2024-12-10' AND '2024-12-23'").df().to_dict('records')}
    accepted=[]; overlaps=[]
    for date in expected:
        left,right=dolt[date],alpaca[date]
        if not executable_raw_bar(left) or not executable_raw_bar(right):raise ValueError('non executable SMR raw quote')
        differences={k:abs(float(left[k])/float(right[k])-1) for k in ['open','high','low','close']}
        if max(differences.values())>.03:raise ValueError('SMR independent price disagreement')
        accepted.append({**right,'security_id':smr,'scope':'possible holding continuation only; no retroactive population/feature merge'})
        overlaps.append({'date':date,'relative_ohlc_difference':differences})
    dump(out/'accepted-holding-prices.json',{'bars':accepted,'identity_source_sha256':file_hash(stage/'target-evidence/focused-primary-web.json'),
        'price_sources':[freeze_file(stage/'target-evidence/raw-alpaca-probe.json'),freeze_file(base/'raw-source.duckdb')],
        'overlap_checks':overlaps,'identity_available_on':'2023-06-02','cik':'1822966','share_class':'A common',
        'mapping_scope':[min(expected),max(expected)],'global_master_merge':False,'native_bundle_installed':False})
    accepted_keys={(smr,b['date']) for b in accepted}; corrected=[]; scopes={}
    for p,rows in candidates['profiles'].items():
        execution=defaultdict(set)
        for signal in scanners[p]['rows']:
            i=calendar.index(signal['signal_date']);execution[signal['security_id']].update(d for d in calendar[i+1:i+12] if d<=rules['window'][2])
        for row in rows:
            sid=row['security_id']; mappings=ids[sid]['mappings']
            if sid==smr:
                mappings=mappings+[{'valid_from':min(expected),'valid_to':max(expected)}]
                row['identity']={'pass':True,'level':'scoped-primary-verified','method':'dated CIK + official Class A common; unchanged historical episode descriptions; holding continuation scoped through Dec23'}
            gaps=holding_mapping_gaps(mappings,sorted(execution[sid]))
            if row['lifecycle_ambiguity'] and not gaps:corrected.append({'profile':p,'security_id':sid,'symbols':row['symbols']})
            row['lifecycle_ambiguity']=bool(gaps);row['holding_mapping_gap_dates']=gaps
            row['missing_execution_sessions']=[d for d in row['missing_execution_sessions'] if (sid,d) not in accepted_keys]
            halt=any(b['symbol'] in row['symbols'] and b['date'] in execution[sid] for b in zero)
            row['known_non_executable_halt']=halt
            row['material_unresolved']=bool(row['price_action_anomalies'] or gaps or row['unverified_split_events'] or halt)
        scopes[p]={'candidate_ids':len(rows),'signals':len(scanners[p]['rows']),
            'identity_unresolved':sum(not r['identity']['pass'] for r in rows),
            'execution_price_gaps':sum(len(r['missing_execution_sessions']) for r in rows),
            'required_execution_prices':sum(r['required_execution_sessions'] for r in rows),
            'material_unresolved':sum(r['material_unresolved'] for r in rows),
            'split_or_lifecycle_ambiguity_ids':sum(bool(r['unverified_split_events']) or r['lifecycle_ambiguity'] for r in rows),
            'known_halt_ids':sum(r['known_non_executable_halt'] for r in rows),
            'source_disagreement_ids':sum(r['source_disagreement'] for r in rows),
            'candidate_feature_price_gaps':sum(r['feature_price_missing'] for r in rows)}
    dump(out/'candidate-audit.json',{'profiles':candidates['profiles'],'scopes':scopes,'lifecycle_false_flags_corrected':corrected,
        'coverage':'original frozen feature store plus accepted scoped holding supplement; not a released Native dataset'})
    core={r['date']:r['security_ids'] for r in read(stage/'universe-d.json')['days']}
    stress=score_stress(scanners['C']['rows'],remaining,core)
    dump(out/'score-stress.json',stress)
    impact=missingness_envelope(daily_top(scanners['C']['rows'],list(remaining)),remaining)
    dump(out/'missingness-impact.json',impact)
    findings=read(stage/'resolved-scope/readiness.json')['findings']; cs=scopes['C']
    findings.update(maximum_daily_true_competitors=max(d['effective_core_uncertainty'] for d in summary),
        candidate_identity_unresolved=cs['identity_unresolved'],candidate_execution_gaps=cs['execution_price_gaps'],
        candidate_material_unresolved=cs['material_unresolved'],known_split_terminal_unresolved=cs['split_or_lifecycle_ambiguity_ids'],
        maximum_unknown_changed_top3_slots=impact['maximum_daily_changed_slots'])
    result=scoped_readiness(findings,rules)
    if result['ready']:raise ValueError('new release requires verified real Native dataset; no silent success')
    dump(out/'readiness.json',{'findings':findings,'result':result,'thresholds_unchanged':True,'old_research_dependency':old_gate['dependency_sha256']})
    queue=Counter(sid for sids in remaining.values() for sid in sids)
    rank=read(stage/'core-rank-stability.json');rank_items={}
    for day in rank['days']:
        for item in day['competitors']:
            if item['security_id'] in remaining[day['date']]:
                rank_items.setdefault(item['security_id'],[]).append(item)
    priority=[]
    for sid,n in queue.items():
        exact=[r for r in rank_items[sid] if r['dollar_volume_upper'] is not None]
        priority.append({'security_id':sid,'symbols':ids[sid]['symbols'],'decision_days':n,
            'exact_liquidity_days':len(exact),'best_exact_rank':min((r['best_rank'] for r in exact),default=None),
            'priority':'P0-A observed likely/borderline' if exact else 'P0-A unbounded; eligibility not proven'})
    priority.sort(key=lambda r:(not bool(r['exact_liquidity_days']),-r['decision_days'],r['security_id']))
    dump(out/'priority-queue.json',{'competitors':priority,'candidate_prices':[r for r in candidates['profiles']['C'] if r['missing_execution_sessions']],
        'candidate_material':[r for r in candidates['profiles']['C'] if r['material_unresolved']],
        'candidate_identity':[r for r in candidates['profiles']['C'] if not r['identity']['pass']],
        'full_market_cleanup':False})
    evidence={'policy':rules['policy'],'rules_sha256':digest(rules),'status':'PARTIAL / BLOCKED',
        'original_core_unknown_range':[min(d['original_unknown'] for d in summary),max(d['original_unknown'] for d in summary)],
        'effective_core_uncertainty_range':[min(d['effective_core_uncertainty'] for d in summary),max(d['effective_core_uncertainty'] for d in summary)],
        'remaining_distinct_competitors':len(queue),'initial_exact_rank_proofs':2438,
        'recent_daily_floor_proofs':len(prior['additional_irrelevance_proofs']),'focused_proofs':len(proofs),
        'confirmed_core_lower_range':[min(d['confirmed_core_members_lower'] for d in summary),max(d['confirmed_core_members_lower'] for d in summary)],
        'cutoffs':{str(n):[min(d[f'rank_{n}_dollar_volume'] for d in summary),max(d[f'rank_{n}_dollar_volume'] for d in summary)] for n in [950,1000,1050]},
        'candidate_scopes':scopes,'accepted_scoped_holding_rows':len(accepted),'corrected_lifecycle_flags':corrected,
        'sensitivity':read(stage/'universe-sensitivity.json'),'top5':{k:{a:b for a,b in v.items() if a!='days'} for k,v in read(stage/'decision-stability.json')['top5'].items()},
        'missingness':{k:v for k,v in impact.items() if k!='days'},
        'score_stress':{k:v for k,v in stress.items() if k!='days'},
        'dividends':read(stage/'resolved-scope/dividend-exposure.json'),
        'readiness':result,'native_execution':'NOT_RUN','reconciliation':'NOT_RUN','native_metrics':None,
        'coupling':'independent diagnostic gate; existing API/native path retains blocked earlier gate; no Current fallback',
        'artifacts':[freeze_file(p) for p in sorted(out.glob('*.json'))],
        'first_phase_freeze':freeze_file(stage/'rules-freeze.json')}
    dump(root/'reports/evidence/pit-research-final-evidence-2026-10-07.json',evidence)
    print(json.dumps({k:evidence[k] for k in ['effective_core_uncertainty_range','remaining_distinct_competitors','focused_proofs','candidate_scopes','score_stress','readiness']},ensure_ascii=True,indent=2),flush=True)


if __name__=='__main__':main()

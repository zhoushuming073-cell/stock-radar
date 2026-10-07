"""Measured membership/ordinary-dividend/sensitivity evidence, not blanket proof."""
from collections import Counter, defaultdict
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from radar.pit.builder import digest
from radar.pit.features import file_hash
from radar.pit.run import freeze_file, load_dependency, save_dependency
from radar.pit.research import research_readiness
from radar.lab.parameters import research_hash


def dump(path,value): path.write_text(json.dumps(value,indent=2,allow_nan=False),encoding='utf-8')


def dividend_bound(signals,execution_sessions,prices,dividends,position_fraction):
    """Potential cash-yield exposure budget, not realized or bounded portfolio P&L.

    Sum unique issuer/ex-date cash rights using the smallest observed possible
    entry price and maximum allowed allocation. Missing entries remain UNKNOWN.
    Candidates must be supplied before outcomes are examined. Missing candidate
    generation elsewhere still prevents claiming a complete market-wide bound.
    """
    by_price={(str(r['security_id']),str(r['date'])[:10]):float(r['open']) for r in prices}
    by_signal=defaultdict(list)
    for signal in signals: by_signal[signal['security_id']].append(signal)
    exposure={}; unknown=[]; large=[]
    sessions=list(execution_sessions)
    for event in dividends:
        sid=event['security_id'];day=event['date'][:10]
        amount=float(event['amount'])
        if not np.isfinite(amount) or amount<0: unknown.append({'security_id':sid,'date':day,'reason':'invalid dividend amount'});continue
        possible=[]
        for signal in by_signal.get(sid,[]):
            signal_day=signal['signal_date'];index=sessions.index(signal_day)
            allowed=sessions[index+1:index+12]  # frozen 10-session holding + entry/exit boundary
            # Buying at the ex-date open does not earn that dividend.
            if day not in allowed or (allowed and day==allowed[0]): continue
            entry_day=allowed[0] if allowed else None
            entry=by_price.get((sid,entry_day))
            if entry is None or entry<=0: unknown.append({'security_id':sid,'date':day,'reason':'possible entry missing'});continue
            possible.append(amount/entry*position_fraction)
            if amount/entry>.05: large.append({'security_id':sid,'date':day,'ratio':amount/entry})
        if possible: exposure[(sid,day)]=max(possible)
    return {'possible_events':len(exposure),'portfolio_return_upper_bound':None,
            'known_exposure_sum':sum(exposure.values()),
            'unpriced_exposures':unknown,'large_distribution_flags':large,
            'rows':[{'security_id':sid,'date':day,'max_return_contribution':value} for (sid,day),value in sorted(exposure.items())],
            'bound_definition':'potential cash yield: sum maximum 1/3 allocations at possible entry equity; actual final-equity effect requires holdings/equity/reinvestment paths'}


def main():
    root=Path.cwd();out=root/'data/pit/research-grade';old=root/'data/pit/source-breakthrough'
    audit=json.loads((out/'audit.json').read_text());rules=json.loads((root/'config/pit_research_grade_rules.json').read_text())
    dependency=load_dependency(audit['dependency_reference'])
    risks=json.loads((out/'identity-risk.json').read_text())['rows']; ids={r['security_id']:r for r in dependency['dependencies']}
    refs=json.loads((old/'reference-coverage.json').read_text())
    populations=dependency['population']; full_members={sid for p in populations for sid in p['security_ids']}
    # Predetermined hash ordering samples the whole population, including
    # unpriced names; a database-derived sampling frame would hide missingness.
    sample=sorted(full_members,key=lambda sid:digest([rules['policy'],sid]))[:50]
    sample_rows=[]
    for sid in sample:
        r=ids[sid];risk=next(x for x in risks if x['security_id']==sid)
        sample_rows.append({'security_id':sid,'symbols':r['symbols'],'risk_level':risk['level'],
            'raw_missing':risk['raw_missing'],'identity_crosschecked':risk['level']=='A' or risk['strict_verified'],
            'unpriced_retained':True})
    later=[r for r in risks if r['lifecycle_disappearance']]
    # Every sampled disappearing episode remains in all earlier observed
    # populations. Disappearance itself is not labelled legal delisting.
    delisted_sample=sorted(later,key=lambda r:digest(['disappearance',r['security_id']]))[:50]
    membership_anomalies=[]
    for p in populations:
        for sid in p['security_ids']:
            record=ids[sid]
            if record.get('listing_date') and record['listing_date']>p['date']:
                membership_anomalies.append({'date':p['date'],'security_id':sid,'kind':'future_listing'})
            if not any(m['valid_from'][:10]<=p['date']<=(m['valid_to'] or '9999')[:10] for m in record['mappings']):
                membership_anomalies.append({'date':p['date'],'security_id':sid,'kind':'outside_dated_mapping'})
    sizes=[len(p['security_ids']) for p in populations]
    jumps=[{'date':populations[i]['date'],'ratio':sizes[i]/sizes[i-1]-1}
           for i in range(1,len(sizes)) if abs(sizes[i]/sizes[i-1]-1)>.05]
    exchanges=Counter(m['exchange'] for r in dependency['dependencies'] for m in r['mappings'])
    membership={'population_size':{'min':min(sizes),'max':max(sizes),'large_daily_changes':jumps},
        'exchange_mapping_counts':dict(exchanges),'future_listing_anomalies':membership_anomalies,
        'random_sample':sample_rows,'random_sample_identity_unresolved':sum(not r['identity_crosschecked'] for r in sample_rows),
        'disappearance_episode_count':len(later),'later_disappearance_sample':[{
            k:r[k] for k in ['security_id','symbols','level','raw_missing','strict_verified']} for r in delisted_sample],
        'later_disappearance_identity_unresolved':sum(not r['research_identity_pass'] and not r['strict_verified'] for r in delisted_sample),
        'secondary_nasdaq_days':len(refs['membership']['daily_comparisons']),
        'secondary_issuer_snapshot_count':refs['identity']['snapshot_count'],
        'secondary_issuer_coverage_end':max(s['date'][:10] for s in refs['receipts']['cik']),
        'limitation':'Nasdaq monthly snapshots cover the window; dated CIK directory stops February 2025. NYSE/AMEX late-window uncertainty not bounded.'}
    dump(out/'membership-evidence.json',membership)
    sensitivity_path=out/'universe-sensitivity.json'
    diagnostics=json.loads(sensitivity_path.read_text()) if sensitivity_path.exists() else None
    if diagnostics and diagnostics.get('research_dependency'):
        dependency=load_dependency(diagnostics['research_dependency'])
        metadata_path=out/'research-run-metadata.json'
        metadata=json.loads(metadata_path.read_text());metadata['research_source_database']=freeze_file(out/'raw-source.duckdb')
        from radar.lab.universe import LocalSecurityMaster
        master=LocalSecurityMaster(out/'diagnostic-features/security-master.csv',out/'diagnostic-features/security-master-manifest.json')
        provenance=master.provenance().metadata()
        metadata['universe_provenance']=provenance
        metadata['signal_source_provenance']=None
        metadata['host_source_hashes']={k:file_hash(root/k) for k in metadata['host_source_hashes']}
        dataset=metadata['resolved_config']['values']['dataset']
        dataset.update(data_snapshot=metadata['data_snapshot'],source_scanner_run_id=None,
            signal_source_provenance_hash=None,universe_fingerprint=master.fingerprint,
            universe_version=master.manifest['source_version'])
        metadata['resolved_config_hash']=research_hash(metadata['resolved_config']['values'])
        metadata['resolved_config']['hash']=metadata['resolved_config_hash']
        dependency['resolved_config_hash']=metadata['resolved_config_hash']
        dependency['files'][str(Path(__file__).resolve())]=freeze_file(Path(__file__))
        dependency['dependency_sha256']=digest({k:v for k,v in dependency.items() if k!='dependency_sha256'})
        diagnostics['research_dependency']=save_dependency(root,dependency)
        dump(sensitivity_path,diagnostics)
        audit['vendor_dependency_reference']=json.loads((out/'rules-freeze.json').read_text())['dependency']
        audit['dependency_reference']=diagnostics['research_dependency']
        audit['dependency_sha256']=dependency['dependency_sha256']
        audit['scope']['missing_prices']=sum(len(r['missing_sessions']) for r in dependency['dependencies']+dependency['benchmarks'])
        audit['gates']['Research price']['reasons']=[f"{audit['scope']['missing_prices']} required raw sessions absent/outside mapping; identity/price conflicts retained"]
        audit['gates']['Causal integrity']['reasons']=['raw causal feature formulas reconstructed; full high-risk identity/material-action input audit incomplete']
        dump(metadata_path,metadata)
    divscan=json.loads((out/'dividend-scan.json').read_text()); events=[]; by_symbol=defaultdict(list)
    for r in dependency['dependencies']:
        for m in r['mappings']: by_symbol[m['symbol']].append((r['security_id'],m))
    for event in divscan.get('events',[]):
        day=event['date'][:10]
        for sid,m in by_symbol.get(event['symbol'],[]):
            if m['valid_from'][:10]<=day<=(m['valid_to'] or '9999')[:10]:
                events.append({**event,'date':day,'security_id':sid})
    if diagnostics:
        candidate_signals=[{'security_id':r['security_id'],'signal_date':r['signal_date']} for r in
                           json.loads((out/'scanner-A.json').read_text())['rows'] if r['selected']]
    else: candidate_signals=dependency['signals']
    with duckdb.connect(str(out/'raw-source.duckdb'),read_only=True) as c:
        mappings=pd.DataFrame([m for r in dependency['dependencies'] for m in r['mappings']])
        c.register('mapping',mappings)
        prices=c.execute("""SELECT b.date,m.security_id,b.open FROM daily_bars b JOIN mapping m ON b.symbol=m.symbol
            AND b.date BETWEEN CAST(m.valid_from AS DATE) AND CAST(m.valid_to AS DATE)""").df().to_dict('records')
    bounds=dividend_bound(candidate_signals,dependency['sessions'],prices,events,1/3)
    bounds['scope']='known reconstructed selected signals only; unknown candidates/execution remain unbounded'
    bounds['source_version']=divscan['source_version'];bounds['cash_event_rows_in_closure']=len(events)
    dump(out/'dividend-exposure.json',bounds)
    # Risk-driven negative scan: not 6421 individual legal no-event documents.
    large_ids={r['security_id'] for r in bounds['large_distribution_flags']}
    no_material=[r['security_id'] for r in risks if r['research_identity_pass'] and not r['material_review_required']
                 and not r['source_price_conflict']
                 and r['security_id'] not in large_ids]
    action={'research_no_material_action_pass':len(no_material),'security_ids':no_material,
        'material_review_required':sum(r['material_review_required'] or r['security_id'] in large_ids for r in risks),
        'split_security_ids':sum(bool(r['split_events']) for r in risks),
        'disappearance_security_ids':len(later),'anomaly_security_ids':sum('continuity' in ' '.join(r['reasons']) for r in risks),
        'scans':['pinned Dolt split/dividend events','dated primary symbol/name/exchange lifecycle','FINRA OTC hits (limited OTC scope)','raw OHLC discontinuity'],
        'ordinary_dividend_separate':True,'limitations':['no vendor complete event attestation','large distributions require strict review',
          'risk negative scan is source-dependent; unresolved B/C cannot inherit A pass']}
    dump(out/'material-action-risk.json',action)
    if diagnostics:
        audit['sensitivity_profiles']=diagnostics['profiles']
        audit['scope_counts']['actual_raw_diagnostic_candidates']=diagnostics['candidate_scopes']
        lookup={r['security_id']:r for r in risks}
        with duckdb.connect(str(out/'diagnostic-features/pit-research.duckdb'),read_only=True) as c:
            observed={(sid,str(day)) for sid,day in c.execute('SELECT security_id,date FROM daily_bars WHERE security_id IS NOT NULL').fetchall()}
        for profile,scope in audit['scope_counts']['actual_raw_diagnostic_candidates'].items():
            candidate_ids=set(scope['security_ids'])
            rows=json.loads((out/('scanner-'+profile+'.json')).read_text())['rows']
            possible_execution=set()
            for row in rows:
                if not row['selected']:continue
                index=dependency['sessions'].index(row['signal_date'])
                possible_execution.update((row['security_id'],day) for day in dependency['sessions'][index+1:index+12])
            execution_missing=len(possible_execution-observed)
            scope.update(identity_blocked=sum(not lookup[s]['research_identity_pass'] and not lookup[s]['strict_verified'] for s in candidate_ids),
                         missing_execution_prices=execution_missing,
                         required_execution_prices=len(possible_execution),
                         material_review_required=sum(lookup[s]['material_review_required'] for s in candidate_ids))
    # Update evidence statuses; PARTIAL means it cannot close Membership.
    def check(name,status,explanation):
        audit['membership']['checks'][name].update(status=status,explanation=explanation)
    check('future_listing','PASS' if not membership_anomalies else 'FAIL','no known future listing/outside dated mapping admitted; unknown true IPO dates disclosed')
    check('population_size','PASS' if not jumps else 'FAIL',f'observed range {min(sizes)}–{max(sizes)}; >5% daily changes {len(jumps)}')
    check('random_sample','PASS' if not membership['random_sample_identity_unresolved'] else 'PARTIAL','50 hash-selected IDs include missing prices; no price-based sampling')
    check('later_delisted_sample','PASS' if not membership['later_disappearance_identity_unresolved'] else 'PARTIAL','50 disappearing episodes sampled without outcome selection; legal delisting status not inferred')
    check('disappearance','PARTIAL','disappearing episodes retained; economic terminal identity/terms not all resolved')
    if diagnostics:
        check('universe_sensitivity',diagnostics['scanner_comparison']['status'],'same frozen Strategy 2/raw causal formulas; unknown population impact remains unbounded')
    audit['ordinary_dividend']={'portfolio_return_bound':None,'measured_known_candidate_upper_bound':bounds['portfolio_return_upper_bound'],
        'measured_cash_yield_exposure_budget':bounds['known_exposure_sum'],
        'scope':bounds['scope'],'reason':'known-candidate bound does not certify unknown candidates or failed-security strata'}
    audit['scope']['unhandled_material_actions']=action['material_review_required']
    audit['gates']['Material corporate actions']['reasons']=[f"{action['material_review_required']} material reviews; {len(no_material)} risk no-material passes; ordinary dividend known-candidate bound {bounds['portfolio_return_upper_bound']}"]
    additional=[out/'membership-evidence.json',out/'dividend-exposure.json',out/'material-action-risk.json',Path(__file__),
        root/'src/radar/pit/research.py',root/'src/radar/pit/execution.py',root/'src/radar/lean/integration.py',
        root/'src/radar/local_api.py',root/'site/dist/lab.js',root/'scripts/audit_pit_research_grade.py',
        out/'accepted-prices.manifest.json',out/'accepted-prices.duckdb']
    public_review=root/'config/pit_public_price_review.json'
    reviewed=json.loads(public_review.read_text())
    additional.extend([public_review,root/'data/pit/raw/public-prices'/(reviewed['license_raw_sha256']+'.raw'),
                       root/'data/pit/raw/public-prices'/reviewed['adjustment_evidence_file']])
    if diagnostics: additional.extend([sensitivity_path,*[out/('scanner-'+p+'.json') for p in 'ABC'],
                                     out/'diagnostic-features/pit-research.duckdb',root/'scripts/build_pit_research_diagnostics.py'])
    if diagnostics and diagnostics.get('research_dependency'): additional.append(Path(diagnostics['research_dependency']['path']))
    existing={f['path']:f for f in audit['files']}
    for p in additional: existing[str(p.resolve())]=freeze_file(p)
    audit['files']=list(existing.values()); hashes=[f['sha256'] for f in audit['files']]
    for gate in audit['gates'].values(): gate['evidence_hashes']=hashes
    for item in audit['membership']['checks'].values(): item['evidence_hashes']=hashes
    audit['audit_sha256']=digest({k:v for k,v in audit.items() if k!='audit_sha256'})
    dump(out/'audit.json',audit);final_readiness=research_readiness(dependency,audit,rules,verify=False)
    dump(out/'readiness.json',final_readiness)
    if diagnostics and diagnostics.get('research_dependency'):
        metadata.update(pit_dependency=diagnostics['research_dependency'],run_pit_readiness=final_readiness,
            pit_research_audit=freeze_file(out/'audit.json'),pit_research_rules=freeze_file(root/'config/pit_research_grade_rules.json'))
        dump(metadata_path,metadata)
    print('Final empirical evidence',json.dumps({'membership':{k:v for k,v in membership.items() if 'sample' not in k},
        'action_pass':len(no_material),'material_reviews':action['material_review_required'],
        'dividend_bound':bounds['portfolio_return_upper_bound']}),flush=True)


if __name__=='__main__': main()

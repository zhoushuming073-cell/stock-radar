"""Reproducible risk audit and raw-price staging, with no production installation.

The frozen full closure stays the denominator. Classification by unavailable
future evidence cannot remove a past member. Raw and legacy adjusted series
are compared, never spliced. Large raw files stay in the ignored PIT cache.
"""
from collections import Counter, defaultdict
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil

import duckdb
import numpy as np
import pandas as pd

from download_pit_research_prices import parse_aggregate
from radar.pit.builder import digest
from radar.pit.features import file_hash
from radar.pit.research import classify_identity, price_anomalies, research_readiness, POLICY
from radar.pit.run import load_dependency, readiness, freeze_file
from radar.pit.sources import effective_day
from radar.schema import ensure_schema


def dump(path, value):
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')


def main():
    root=Path.cwd(); out=root/'data/pit/research-grade'; old=root/'data/pit/source-breakthrough'
    rules=json.loads((root/'config/pit_research_grade_rules.json').read_text(encoding='utf-8'))
    freeze=json.loads((out/'rules-freeze.json').read_text())
    if freeze['rules_sha256']!=file_hash(root/'config/pit_research_grade_rules.json'):
        raise ValueError('rules changed after freeze')
    manifest=load_dependency(freeze['dependency']); strict=readiness(manifest)
    print('Strict closure physically verified',flush=True)
    source=json.loads((out/'raw-price-receipts.json').read_text())
    if not source['complete'] or source['dependency_sha256']!=manifest['dependency_sha256']:
        raise ValueError('whole raw download incomplete; no partial acceptance')
    cache=root/'data/pit/raw/research-grade'; records=manifest['dependencies']; ids={r['security_id']:r for r in records}
    mapping=pd.DataFrame([m for r in records for m in r['mappings']])
    mapping['valid_from']=pd.to_datetime(mapping.valid_from)
    mapping['valid_to']=pd.to_datetime(mapping.valid_to).fillna(pd.Timestamp('2050-12-31'))
    ref=json.loads((old/'reference-coverage.json').read_text())
    snapshot_dates={s['sha']:str(effective_day(s['date'].replace('Z','+00:00')))
                    for s in ref['receipts']['cik']}
    observations={r['security_id']:[{**o,'available_on':snapshot_dates[o['snapshot']]} for o in r['dated_issuer_candidates']]
                  for r in ref['identity']['rows']}
    finra=json.loads((old/'bulk-reference-samples.json').read_text())['finra']
    otc_risk={r['security_id'] for r in finra['candidates'] if r['dated_candidate_hits']}
    splits=json.loads((out/'split-scan.json').read_text()); dividends=json.loads((out/'dividend-scan.json').read_text())
    for scan in (splits,dividends):
        for event in scan.get('events',[]): event['date']=str(event['date'])[:10]
    by_split=defaultdict(list)
    for event in splits.get('events',[]): by_split[event['symbol']].append(event)
    all_mappings=pd.read_csv(root/'data/security-master.csv',keep_default_na=False)
    collision_symbols=set(all_mappings.groupby('symbol').security_id.nunique().loc[lambda x:x>1].index)
    collision_known={}
    for symbol,group in all_mappings.groupby('symbol'):
        dates=sorted(group.groupby('security_id').valid_from.min().str[:10])
        if len(dates)>1: collision_known[symbol]=dates[1]
    # Preserve a new raw source with the existing DuckDB schema. No old database
    # is attached writable; receipt validation precedes each insert.
    raw_db=out/'raw-source.duckdb'; staging=out/'raw-source.building.duckdb'
    if not raw_db.exists():
        if staging.exists(): raise ValueError('unfinished raw staging exists; inspect before retry')
        wanted=set(mapping.symbol)|{'SPY','QQQ'}
        with duckdb.connect(str(staging)) as c:
            ensure_schema(c)
            invalid_count=0
            for i,item in enumerate(source['sessions']):
                receipt=item['receipt']; path=cache/(receipt['sha256']+'.raw')
                if file_hash(path)!=receipt['sha256']: raise ValueError('raw OHLC receipt changed')
                response=json.loads(path.read_text())
                bars=parse_aggregate(response['rows'],item['date'],None)
                payload=pd.DataFrame([r for r in bars if r[0] in wanted],
                                     columns=['symbol','open','high','low','close','volume'])
                for column in ['open','high','low','close','volume']: payload[column]=pd.to_numeric(payload[column])
                valid=(np.isfinite(payload.iloc[:,1:]).all(axis=1)&payload.low.gt(0)&payload.volume.ge(0)
                       &payload.volume.eq(np.floor(payload.volume))&payload.open.between(payload.low,payload.high)
                       &payload.close.between(payload.low,payload.high))
                invalid_count+=int((~valid).sum()); payload=payload.loc[valid].copy()
                payload['date']=item['date']; payload['downloaded_at']=receipt['captured_at']
                c.register('payload',payload)
                c.execute("""INSERT INTO daily_bars SELECT symbol,CAST(date AS DATE),open,high,low,close,
                    CAST(volume AS BIGINT),NULL,NULL,'Dolt','post-no-preference/stocks','raw',
                    CAST(downloaded_at AS TIMESTAMPTZ) FROM payload""")
                c.unregister('payload')
                if i%50==0: print('Staged raw date',i+1,'/',len(source['sessions']),flush=True)
            c.execute('CHECKPOINT')
        staging.rename(raw_db)
        dump(out/'raw-source.manifest.json',{'database_sha256':file_hash(raw_db),'source_version':source['pin'],
             'license':source['license'],'raw_invalid_rows':invalid_count,'receipt_sha256':file_hash(out/'raw-price-receipts.json'),
             'research_rules_sha256':digest(rules),'identity_status':'unresolved rows remain quarantined',
             'feature_use':'diagnostic only until research gates PASS','adjustment':'raw'})
    raw_manifest=json.loads((out/'raw-source.manifest.json').read_text())
    if raw_manifest['database_sha256']!=file_hash(raw_db) or raw_manifest['receipt_sha256']!=file_hash(out/'raw-price-receipts.json'):
        raise ValueError('raw dataset/receipts changed')
    with duckdb.connect(str(raw_db),read_only=True) as c:
        c.register('mapping',mapping)
        bars=c.execute("""SELECT b.*,m.security_id FROM daily_bars b JOIN mapping m
            ON b.symbol=m.symbol AND b.date BETWEEN m.valid_from AND m.valid_to ORDER BY m.security_id,b.date""").df()
    bars['date']=bars.date.dt.strftime('%Y-%m-%d')
    # Raw-vs-adjusted disagreements remain quarantined until their basis is
    # explained; changing source alone must not silently change price levels.
    with duckdb.connect() as c:
        c.register('raw',bars[['security_id','date','close']])
        legacy=next(v['path'] for v in manifest['files'].values() if Path(v['path']).name=='pit-research.duckdb')
        c.execute("ATTACH '"+legacy.replace("'","''")+"' AS legacy (READ_ONLY)")
        disagreement=c.execute("""SELECT r.security_id,COUNT(*) AS overlaps,
            SUM(CASE WHEN ABS(r.close/b.close-1)>? THEN 1 ELSE 0 END) AS disagreements,
            MAX(ABS(r.close/b.close-1)) AS maximum_relative_disagreement
            FROM raw r JOIN legacy.daily_bars b ON r.security_id=b.security_id AND CAST(r.date AS DATE)=b.date
            WHERE b.close>0 GROUP BY 1""",[rules['prices']['cross_source_relative_tolerance']]).df()
    price_conflicts=set(disagreement.loc[disagreement.disagreements.gt(0),'security_id'])
    dump(out/'source-disagreement.json',json.loads(disagreement.to_json(orient='records')))
    groups=dict(tuple(bars.groupby('security_id')))
    risk=[]; accepted=[]; accepted_gaps=0; anomalies=[]; raw_missing=0; raw_execution_missing=0
    full_price_required=sum(len(r['required_sessions']) for r in records)
    selected={s['security_id'] for s in manifest['signals']}
    for i,r in enumerate(records):
        sid=r['security_id']; frame=groups.get(sid,bars.iloc[:0])
        frame=frame.loc[frame.date.isin(r['required_sessions'])]
        findings=price_anomalies(frame,rules)
        anomalous=bool(findings)
        events=[e for s in r['symbols'] for e in by_split.get(s,[]) if e['date'] in r['required_sessions']]
        lifecycle=any(m['valid_to'] is not None and m['valid_to'][:10]<manifest['window'][2] for m in r['mappings'])
        finding=classify_identity(r,observations.get(sid,[]),rules,
            collision=bool(set(r['symbols'])&collision_symbols),event_risk=bool(events or sid in otc_risk or lifecycle),
            price_continuous=not anomalous and not frame.empty)
        strict_verified=all(m.get('resolution_status')=='verified' and m.get('classification_confidence')=='verified'
                            and m.get('identity_evidence_hash') for m in r['mappings'])
        present=set(frame.date); missing=sorted(set(r['required_sessions'])-present)
        execution_missing=sorted(set(r['execution_sessions'])-present)
        raw_missing+=len(missing); raw_execution_missing+=len(execution_missing)
        high_material=bool(events or sid in otc_risk or lifecycle or anomalous or r['actions'])
        finding.update(security_id=sid,symbols=r['symbols'],strict_verified=strict_verified,
                       required_prices=len(r['required_sessions']),raw_missing=len(missing),
                       raw_execution_missing=len(execution_missing),split_events=events,
                       lifecycle_disappearance=lifecycle,material_review_required=high_material,
                       source_price_conflict=sid in price_conflicts,
                       missing_sessions=missing,identity_scope='validation-only; never historical selection filter')
        risk.append(finding)
        anomalies.extend({'security_id':sid,**a} for a in findings)
        if finding['research_identity_pass'] and not high_material and sid not in price_conflicts:
            for row in frame.to_dict('records'):
                accepted.append(row)
                if row['date'] in r['missing_sessions']: accepted_gaps+=1
        if i%1000==0: print('Risk classified',i+1,'/',len(records),flush=True)
    # Raw accepted prices are a separate table; no splice with the legacy split
    # series and no mutation of the global security-master trust flags.
    accepted_db=out/'accepted-prices.duckdb'
    accepted_frame=pd.DataFrame(accepted,columns=bars.columns)
    if not accepted_db.exists():
        with duckdb.connect(str(accepted_db)) as c:
            c.register('accepted',accepted_frame)
            c.execute('CREATE TABLE daily_bars AS SELECT * REPLACE (CAST(date AS DATE) AS date) FROM accepted')
            c.execute('CHECKPOINT')
    else:
        with duckdb.connect(str(accepted_db),read_only=True) as c:
            c.register('accepted',accepted_frame)
            if c.execute('''SELECT COUNT(*) FROM ((SELECT * FROM daily_bars EXCEPT SELECT * FROM accepted)
                UNION ALL (SELECT * FROM accepted EXCEPT SELECT * FROM daily_bars))''').fetchone()[0]:
                raise ValueError('accepted price inputs changed; use a new versioned directory')
    identity_counts=dict(Counter(r['level'] for r in risk)); risk_by={r['security_id']:r for r in risk}
    dump(out/'identity-risk.json',{'counts':identity_counts,'rows':risk})
    dump(out/'price-anomalies.json',{'counts':dict(Counter(a['kind'] for a in anomalies)),'rows':anomalies})
    dump(out/'accepted-prices.manifest.json',{'database':str(accepted_db.resolve()),'database_sha256':file_hash(accepted_db),
         'quality_tier':'research-grade','status':'accepted_price_rows; portfolio readiness separate',
         'rows':len(accepted),'new_missing_rows_recovered':accepted_gaps,'source_version':source['pin'],
         'license':source['license'],'attribution':'post-no-preference/stocks on DoltHub (CC-BY-SA-4.0)',
         'price_basis':'raw','rules_sha256':digest(rules),'dependency_sha256':manifest['dependency_sha256'],
         'identity_risk_sha256':file_hash(out/'identity-risk.json'),'source_receipts_sha256':file_hash(out/'raw-price-receipts.json'),
         'limitations':['ordinary dividend impact separate','public EOD not consolidated SIP','no global class certification',
                        'accepted rows do not certify full features/portfolio','no mixed legacy/Dolt identity series']})
    # Core uses lagged raw prices; explicit UNKNOWN competitors survive.
    with duckdb.connect() as c:
        c.register('bars',bars[['security_id','date','open','high','low','close','volume']])
        c.register('calendar',pd.DataFrame({'date':manifest['calendar'],'session_index':range(len(manifest['calendar']))}))
        core_inputs=c.execute("""WITH ordered AS (SELECT b.*,c.session_index,close*volume AS dollars FROM bars b
            JOIN calendar c USING(date)), rolling AS (SELECT *,COUNT(*) OVER h AS history_count,
            MIN(session_index) OVER h AS first_index,AVG(dollars) OVER l AS avg_dollars,
            COUNT(*) OVER l AS recent_count,MIN(dollars) OVER l AS min_dollars FROM ordered WINDOW
            h AS (PARTITION BY security_id ORDER BY date ROWS BETWEEN 125 PRECEDING AND CURRENT ROW),
            l AS (PARTITION BY security_id ORDER BY session_index RANGE BETWEEN 19 PRECEDING AND CURRENT ROW))
            SELECT * FROM rolling""").df()
    core_by_day={day:frame.set_index('security_id') for day,frame in core_inputs.groupby('date')}
    calendar=manifest['calendar']; core=[]; b_days=[]; risk_cache={}
    for population in manifest['population']:
        day=population['date']; prev=calendar[calendar.index(day)-1]
        inputs=core_by_day.get(prev,pd.DataFrame()); ranked=[];unknown=[];rejected={}; strict_asof=[]
        for sid in population['security_ids']:
            record=ids[sid]
            current=[m for m in record['mappings'] if m['valid_from'][:10]<=day<=(m['valid_to'] or '9999')[:10]]
            if len(current)!=1: unknown.append(sid);continue
            m=current[0]
            known_mappings=[x for x in record['mappings'] if x['valid_from'][:10]<=day]
            past_record={**record,'mappings':known_mappings,'actions':[a for a in record['actions'] if a['effective_date']<=day]}
            dated_obs=observations.get(sid,[])
            past_splits=[e for s in record['symbols'] for e in by_split.get(s,[]) if e['date']<=day and e['date'] in record['required_sessions']]
            # Future episodes never affect a past stricter profile.
            past_collision=any(collision_known.get(s,'9999')<=day for s in {x['symbol'] for x in known_mappings})
            cache_key=(sid,sum(o['available_on']<=day for o in dated_obs),len(known_mappings),
                       bool(past_splits),past_collision,len(past_record['actions']))
            if cache_key not in risk_cache:
                risk_cache[cache_key]=classify_identity(past_record,dated_obs,rules,as_of=day,collision=past_collision,
                                                      event_risk=bool(past_splits),price_continuous=True)
            past_risk=risk_cache[cache_key]
            if past_risk['research_identity_pass']: strict_asof.append(sid)
            if m.get('listing_date') and m['listing_date'][:10]>day:
                rejected[sid]='future_ipo';continue
            if inputs.empty or sid not in inputs.index: unknown.append(sid);continue
            row=inputs.loc[sid]
            if row.close<rules['core']['price_floor']: rejected[sid]='known_price_floor';continue
            if row.min_dollars<rules['core']['minimum_daily_dollar_volume']:
                rejected[sid]='known_daily_liquidity_rule';continue
            if row.recent_count==20 and row.avg_dollars<rules['core']['minimum_avg_dollar_volume']:
                rejected[sid]='known_average_liquidity_rule';continue
            if row.history_count<126 or row.session_index-row.first_index!=125:
                unknown.append(sid);continue
            if row.avg_dollars<rules['core']['minimum_avg_dollar_volume'] or row.min_dollars<rules['core']['minimum_daily_dollar_volume']:
                rejected[sid]='known_liquidity_rule';continue
            ranked.append((sid,float(row.avg_dollars)))
        ranked.sort(key=lambda x:(-x[1],x[0]));cap=rules['core']['target_size']
        core.append({'date':day,'security_ids':[x[0] for x in ranked[:cap]],'unknown_security_ids':sorted(unknown),
                     'eligible_before_cap':len(ranked),'rejected_counts':dict(Counter(rejected.values())),
                     'possible_rank_displacement':min(cap,len(unknown)),'causal_cutoff':prev,'definitive':not unknown})
        b_days.append({'date':day,'security_ids':sorted(strict_asof),
                       'interpretation':'causal identity screen, missing prices remain in audit denominator'})
        if len(core)%30==0: print('Core causal day',len(core),'/',len(manifest['population']),flush=True)
    dump(out/'core-universe.json',{'policy_sha256':digest(rules),'target_size':1000,'days':core,
         'status':'provisional until unknown rank competitors bounded','selection_uses_future':False})
    dump(out/'universe-b.json',{'days':b_days,'selection_uses_future':False})
    admitted={sid for d in core for sid in d['security_ids']}; possible=admitted|{sid for d in core for sid in d['unknown_security_ids']}
    membership_checks={name:{'status':'FAIL','reason':'not validated'} for name in
        ['historical_primary','historical_secondary','future_listing','disappearance','population_size',
         'exchange_coverage','random_sample','later_delisted_sample','universe_sensitivity']}
    membership_checks['historical_primary']={'status':'PASS','explanation':'dated primary Git population and unchanged full closure'}
    membership_checks['population_size']={'status':'PASS','explanation':'daily observed sizes inspected; no completeness inference',
        'min':min(len(d['security_ids']) for d in manifest['population']),
        'max':max(len(d['security_ids']) for d in manifest['population'])}
    membership_checks['historical_secondary']={'status':'PARTIAL','reason':'Nasdaq historical cross-check; NYSE/AMEX second source absent',
        'days':len(ref['membership']['daily_comparisons'])}
    membership_checks['exchange_coverage']={'status':'PARTIAL','reason':'primary 3 exchanges; historical secondary covers Nasdaq only'}
    material_count=sum(r['material_review_required'] for r in risk)
    scopes={'full_historical':{'securities':len(records),'identity_blocked':sum(not r['research_identity_pass'] and not r['strict_verified'] for r in risk),
            'raw_missing':raw_missing,'legacy_missing':strict['missing_prices'],'material_review_required':material_count},
        'research_eligible_validation_A':{'securities':identity_counts.get('A',0),'accepted_price_rows':len(accepted),
            'raw_missing':sum(r['raw_missing'] for r in risk if r['level']=='A'),'material_review_required':sum(r['material_review_required'] for r in risk if r['level']=='A'),
            'selection_warning':'validation stratum, not a retrospective historical filter'},
        'actual_legacy_candidates_possible_holdings':{'securities':len(selected),'signals':len(manifest['signals']),
            'identity_blocked':sum(not risk_by[s]['research_identity_pass'] and not risk_by[s]['strict_verified'] for s in selected),
            'raw_execution_missing':raw_execution_missing,'material_review_required':sum(risk_by[s]['material_review_required'] for s in selected)},
        'core_provisional':{'admitted_ids':len(admitted),'possible_ids_including_unknown':len(possible),
            'raw_missing_admitted':sum(risk_by[s]['raw_missing'] for s in admitted),
            'raw_missing_possible':sum(risk_by[s]['raw_missing'] for s in possible),
            'daily_admitted_min':min(len(d['security_ids']) for d in core),'daily_admitted_max':max(len(d['security_ids']) for d in core),
            'daily_unknown_min':min(len(d['unknown_security_ids']) for d in core),'daily_unknown_max':max(len(d['unknown_security_ids']) for d in core)}}
    dump(out/'scope-counts.json',scopes)
    # Evidence files are frozen for every tier; PASS requires actual measured
    # uncertainty bounds, not merely lowering the old certification threshold.
    files=[freeze_file(p) for p in [out/'identity-risk.json',out/'price-anomalies.json',out/'raw-price-receipts.json',
            out/'raw-source.manifest.json',out/'split-scan.json',out/'dividend-scan.json',out/'core-universe.json',
            out/'universe-b.json',out/'source-disagreement.json',out/'scope-counts.json',out/'accepted-prices.manifest.json',accepted_db,
            raw_db,root/'config/pit_research_grade_rules.json',root/'src/radar/pit/research.py',Path(__file__)]]
    hashes=[p['sha256'] for p in files]
    for check in membership_checks.values(): check['evidence_hashes']=hashes
    gates={g:{'status':'FAIL','evidence_hashes':hashes,'explanation':'run-specific empirical audit',
               'reasons':['not yet validated']} for g in
        ['Causal integrity','Research identity','Research membership','Research price','Material corporate actions','Terminal','LEAN Input']}
    unresolved=scopes['full_historical']['identity_blocked']
    gates['Research identity'].update(status='PASS' if not unresolved else 'FAIL',reasons=[f'{unresolved} B/C identities remain unresolved'])
    gates['Research price']['reasons']=[f'{raw_missing} raw price sessions absent/outside legal mapping; old closure still adjusted']
    gates['Material corporate actions']['reasons']=[f'{material_count} securities need material review; dividend impact unbounded']
    gates['Research membership']['reasons']=['NYSE/AMEX second-source coverage and missing rank competitors unbounded; sensitivity pending']
    gates['Causal integrity']['reasons']=['legacy execution closure uses split-adjusted prices; new raw features not installed/certified']
    gates['Terminal'].update(status=strict['scorecard']['Terminal'],reasons=strict['reasons_by_gate']['Terminal'])
    audit={'policy':POLICY,'dependency_sha256':manifest['dependency_sha256'],'dependency_reference':freeze['dependency'],
        'rules_sha256':digest(rules),'files':files,'gates':gates,'membership':{'checks':membership_checks},
        'scope':{'unresolved_identities':unresolved,'missing_prices':strict['missing_prices'],
                 'unhandled_material_actions':material_count,'unhandled_terminals':len(strict['reasons_by_gate']['Terminal']),
                 'unbounded_unknown_members':len(possible-admitted)},
        'scope_counts':scopes,'identity_decisions':{r['security_id']:{'level':r['level'],
            'observations':observations.get(r['security_id'],[]),'collision':bool(set(r['symbols'])&collision_symbols),
            'event_risk':r['material_review_required'],'price_continuous':r['level']=='A'} for r in risk},
        'sensitivity_profiles':{},'ordinary_dividend':{'portfolio_return_bound':None,
            'reason':'source event amounts cannot bound unknown holdings/ranking until candidates/execution reconstructed'},
        'causal_verified':False,'hard_failures':[]}
    audit['audit_sha256']=digest(audit);dump(out/'audit.json',audit)
    report=research_readiness(manifest,audit,rules,verify=False)
    dump(out/'readiness.json',report)
    dump(out/'strict-readiness.json',strict)
    print(json.dumps({'identity':identity_counts,'accepted':len(accepted),'recovered':accepted_gaps,'scopes':scopes},indent=2),flush=True)


if __name__=='__main__': main()

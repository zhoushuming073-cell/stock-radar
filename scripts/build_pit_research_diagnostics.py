"""Recompute raw causal features and compare A/B/C with production Strategy 2.

These are data sensitivity diagnostics, not a certified strategy result. Unknown
members and censored labels remain disclosed. Portfolio returns are generated
only by native LEAN after a research PASS; never by a substitute simulator.
"""
from copy import deepcopy
import json
from pathlib import Path
import shutil

import duckdb
import numpy as np
import pandas as pd

from radar.features.scoring import load_research_config, score_elasticity
from radar.lab.data import load_strategy_segment, load_forward_bars, available_features
from radar.lab.scanner import evaluation_settings, primary_outcome_name, before_adverse_name, candidate_metrics
from radar.lab.scanner_worker import scan_frames
from radar.lab.universe import LocalSecurityMaster
from radar.lab.parameters import plain
from radar.pit.builder import digest
from radar.pit.features import build_features, file_hash
from radar.pit.research import sensitivity
from radar.pit.actions import corporate_actions
from radar.pit.trust import load_catalog
from radar.pit.run import build_dependency, save_dependency, freeze_file
from radar.lean.export import freeze_signals
from radar.strategy.loader import load_strategy_directory


def dump(path, value):
    path.write_text(json.dumps(value,indent=2,allow_nan=False,default=str),encoding='utf-8')


class DiagnosticUniverse:
    """Daily causal filter, with full-market forward identity mapping unchanged."""
    def __init__(self,master,days):
        self.master=master;self.days=days;self.frame=master.frame

    def eligible_on(self,day):
        result=self.master.eligible_on(day); key=str(pd.Timestamp(day).date())
        return result.loc[result.security_id.isin(self.days[key])]

    def filter_frame(self,frame):
        # Labels may extend after a member leaves the Core pool. They continue
        # to use historical identity mappings, never the later Core membership.
        return self.master.filter_frame(frame)


def main():
    root=Path.cwd();out=root/'data/pit/research-grade';build=out/'diagnostic-features';build.mkdir(exist_ok=True)
    source=out/'raw-source.duckdb'; rules=json.loads((root/'config/pit_research_grade_rules.json').read_text())
    freeze=json.loads((out/'rules-freeze.json').read_text()); dependency=json.loads(Path(freeze['dependency']['path']).read_text())
    for name in ['security-master.csv','security-master-manifest.json']:
        path=build/name
        if path.exists() and file_hash(path)!=file_hash(root/'data'/name): raise ValueError('diagnostic master changed')
        if not path.exists(): shutil.copyfile(root/'data'/name,path)
    master=LocalSecurityMaster(build/'security-master.csv',build/'security-master-manifest.json')
    split_scan=json.loads((out/'split-scan.json').read_text()); candidate_splits=[]
    for event in split_scan.get('events',[]):
        event={**event,'date':str(event['date'])[:10]}
        mapped=master.frame.loc[master.frame.symbol.eq(event['symbol'])&master.frame.valid_from.le(pd.Timestamp(event['date']))
                               &master.frame.valid_to.ge(pd.Timestamp(event['date']))]
        if len(mapped)!=1: continue
        to,denominator=float(event['to_factor']),float(event['for_factor'])
        ratio=to/denominator if denominator>0 and to>0 else None
        candidate_splits.append({'security_id':str(mapped.iloc[0].security_id),
                        'event_type':'invalid_split_factor' if ratio is None else 'split' if ratio>=1 else 'reverse_split',
                        'effective_date':event['date'],'to_factor':float(event['to_factor']),
                        'for_factor':float(event['for_factor']), 'confidence':'research_source_candidate',
                        'source':'Dolt pinned split table; publication timing/official handling uncertified'})
    catalog=load_catalog(root/'config/pit_trust_evidence.json',root/'data/pit/raw/official-evidence')
    reviews=json.loads((root/'config/pit_execution_action_reviews.json').read_text())
    actions=[a for a in corporate_actions(catalog,reviews) if a['event_type'] in {'split','reverse_split'}
             and a['confidence']=='verified' and a['handling_mode']=='native_raw_split']
    reviewed={(a['security_id'],a['effective_date']) for a in actions}
    db=build/'pit-research.duckdb'; sidecar=build/'security-master-feature-store.json'
    if not db.exists():
        result=build_features(source,master,root/'config/research.yaml',db,
            lambda p:print('Raw features',p['completed'],'/',p['total'],flush=True),raw_actions=actions)
        dump(sidecar,result)
    master=LocalSecurityMaster(build/'security-master.csv',build/'security-master-manifest.json')
    registration=load_strategy_directory(root/'strategies/full_strategy2_v1',available_features(db),run_tests=True)
    required=set(registration.manifest.required_features)
    start,end,evaluation=map(pd.Timestamp,rules['window'])
    frame=load_strategy_segment(source,start,end,required,master)
    bars=load_forward_bars(source,start,evaluation,master)
    sessions=pd.DatetimeIndex(pd.to_datetime([d for d in dependency['calendar'] if str(start.date())<=d<=str(evaluation.date())]))
    # An uncertified split cannot create a false reversal or -90% return. Mark
    # its contaminated feature window unavailable, retaining membership/unknown
    # competitors. This is a diagnostic limitation, never a bounded exception.
    feature_unavailable=pd.Series(False,index=frame.index)
    full_calendar=pd.DatetimeIndex(pd.to_datetime(dependency['calendar']))
    for event in candidate_splits:
        if (event['security_id'],event['effective_date']) in reviewed: continue
        event_date=pd.Timestamp(event['effective_date'])
        after=full_calendar[full_calendar>=event_date]
        through=after[min(125,len(after)-1)] if len(after) else event_date
        feature_unavailable|=(frame.security_id.eq(event['security_id'])&frame.date.between(event_date,through))
    unavailable_count=int(feature_unavailable.sum())
    frame=frame.loc[~feature_unavailable]
    core=json.loads((out/'core-universe.json').read_text())['days']; b=json.loads((out/'universe-b.json').read_text())['days']
    day_sets={'A':{d['date']:set(d['security_ids']) for d in dependency['population']},
              'B':{d['date']:set(d['security_ids']) for d in b},'C':{d['date']:set(d['security_ids']) for d in core}}
    cfg=load_research_config(root/'config/research.yaml');spec=evaluation_settings(None)
    contract=digest({'strategy_code':file_hash(root/'strategies/full_strategy2_v1/strategy.py'),
        'config':plain(registration.config),'window':rules['window'],'evaluation':spec,
        'execution_config':file_hash(root/'config/backtest.yaml'),'fees':file_hash(root/'config/research.yaml')})
    profiles={};candidate_scopes={}
    a_frame=None
    for profile in 'ABC':
        selected=frame.loc[[sid in day_sets[profile][str(day.date())] for day,sid in
                           zip(frame.date,frame.security_id)]].copy()
        # Recompute the same population percentile formula after each causal
        # screen. Retaining A's percentile rank in B/C would be a different test.
        with duckdb.connect(str(db),read_only=True) as c:
            inputs=c.execute("""SELECT date,symbol,security_id,tradability_pass,elasticity_beta_raw,elasticity_atr_raw,
                elasticity_idio_raw,elasticity_burst_raw,elasticity_hit_raw FROM daily_features WHERE date BETWEEN ? AND ?""",
                [start.date(),end.date()]).df()
        mask=[sid in day_sets[profile][str(day.date())] for day,sid in zip(inputs.date,inputs.security_id)]
        rank_inputs=inputs.loc[mask & inputs.tradability_pass.fillna(False).to_numpy()].copy()
        scores=score_elasticity(rank_inputs,cfg).set_index(['date','symbol']).elasticity_score
        selected['elasticity_score']=selected.index.map(scores)
        if profile=='A': a_frame=selected.copy()
        provider=DiagnosticUniverse(master,day_sets[profile])
        rows,metrics=scan_frames(registration.plugin,registration.config,selected,bars,sessions,start,end,spec,
            progress=lambda p:print('Scanner',profile,p['completed_sessions'],'/',p['total_sessions'],flush=True)
                if p['completed_sessions']%30==0 else None,universe_provider=provider)
        for row in rows:
            index=sessions.get_loc(pd.Timestamp(row['signal_date']))
            last=sessions[min(index+spec['horizon_sessions'],len(sessions)-1)]
            if any(e['security_id']==row['security_id'] and pd.Timestamp(row['signal_date'])<pd.Timestamp(e['effective_date'])<=last
                   for e in candidate_splits):
                row.update(label=None,label_status='censored',label_reason='material_split_in_forward_window')
            row['signal_date']=str(pd.Timestamp(row['signal_date']).date())
        # Background price labels may span unreviewed splits; omit background
        # lift claims and recompute candidate metrics with explicit censoring.
        candidates=pd.DataFrame(rows)
        if rows: candidates['signal_date']=pd.to_datetime(candidates.signal_date)
        else: candidates=pd.DataFrame(columns=['signal_date','symbol','rank','label','label_status','label_reason'])
        measured=candidate_metrics(candidates,pd.DataFrame(columns=['signal_date','symbol','label']),spec,sessions)
        metrics={**measured,'funnel_by_day':metrics['funnel_by_day'],'coverage':metrics['coverage'],
                 'material_feature_rows_unavailable_full_market':unavailable_count,
                 'background_lift':'not evaluated: material-action uncertainty'}
        dump(out/('scanner-'+profile+'.json'),{'profile':profile,'label':'Research-Grade PIT data diagnostic; BLOCKED',
            'quality_tier':'research-grade','contract_sha256':contract,'metrics':metrics,'rows':rows,
            'native_status':'NOT_RUN','limitations':['unresolved identity/action scopes remain','unknown missing competitors unbounded',
                'unreviewed split feature windows unavailable; forward split windows censored',
                'only previously verified official split factors enter features']})
        labeled=[r['label'] for r in rows if r['label_status']=='labeled' and r['label'] is not None]
        primary=primary_outcome_name(spec); path=before_adverse_name(.05,-.05,spec['horizon_sessions'])
        def average(field):
            values=[float(r[field]) for r in labeled if r.get(field) is not None]
            return float(np.mean(values)) if values else None
        profiles[profile]={'contract_sha256':contract,'candidate_ids':[r['signal_date']+'/'+r['security_id'] for r in rows],
            'candidate_count':len(rows),'censored_count':len(rows)-len(labeled),'unknown_impact_bounded':False,
            'win_rate':average(primary),'path_success':average(path),'mfe':average('mfe_10'),'mae':average('mae_10'),
            'native_return':None,'native_drawdown':None,'trade_count':None,'average_trade':None,'fee_equity_fraction':None,
            'win_rate_definition':'Scanner +5% high touch within 10 sessions; not profitable-trade win rate'}
        candidate_scopes[profile]={'security_ids':sorted({r['security_id'] for r in rows}),
            'selected_signal_count':sum(r['selected'] for r in rows),'signals':len(rows)}
    result={'policy_sha256':digest(rules),'contract_sha256':contract,'profiles':profiles,
        'candidate_scopes':candidate_scopes,'scanner_comparison':sensitivity(profiles,rules,stage='scanner'),
        'complete_comparison':sensitivity(profiles,rules),'native_status':'NOT_RUN',
        'scope':'forensic sensitivity on reconstructible inputs; cannot bound wholly missing securities'}
    # A new closure describes the actual raw research dataset and freshly
    # generated signals. The old vendor-grade closure and strict report persist.
    previous=json.loads((root/'data/pit/final-acceptance/formal-run-receipt.json').read_text())
    metadata=deepcopy(previous['point_in_time_backtest']['metadata'])
    metadata.update(source_scanner_run_id=None,quality_tier='research-grade',label='Research-Grade PIT',
                    data_snapshot=file_hash(source),research_source_database=freeze_file(source),config=plain(registration.config))
    metadata['window']=rules['window']
    execution=metadata['resolved_config']['values']['execution']
    if execution['market_guard']['mode']!='none':
        raise ValueError('diagnostic raw signal closure requires explicit PIT benchmark guard handling')
    causal=a_frame.loc[a_frame.tradability_pass.fillna(False)].copy()
    for name in registration.plugin.required_features():
        if name in causal and pd.api.types.is_numeric_dtype(causal[name]):
            causal=causal.loc[np.isfinite(pd.to_numeric(causal[name],errors='coerce'))]
    signals,_=freeze_signals(causal,sessions,metadata,registration.plugin,None,execution)
    paths=[master.csv_path,master.manifest_path,sidecar,db,source,root/'config/research.yaml',
           root/'config/pit_research_grade_rules.json',root/'config/pit_trust_evidence.json',
           root/'config/pit_execution_action_reviews.json',out/'raw-price-receipts.json',
           out/'identity-risk.json',root/'src/radar/pit/research.py',Path(__file__)]
    paths.extend(root/'data/pit/raw/official-evidence'/(s['raw_sha256']+'.raw') for s in catalog['sources'].values())
    closure=build_dependency(master,db,pd.to_datetime(dependency['calendar']),causal,signals,metadata,
        catalog=catalog,certificates={'actions':reviews},files={str(p.resolve()):freeze_file(p) for p in paths})
    reference=save_dependency(root,closure)
    result['research_dependency']=reference
    result['raw_required_prices']=sum(len(r['required_sessions']) for r in closure['dependencies']+closure['benchmarks'])
    result['raw_missing_prices']=sum(len(r['missing_sessions']) for r in closure['dependencies']+closure['benchmarks'])
    result['raw_signals']=len(closure['signals'])
    dump(out/'research-run-metadata.json',metadata)
    dump(out/'universe-sensitivity.json',result)
    print('Diagnostic profiles',json.dumps({k:{x:v for x,v in p.items() if x!='candidate_ids'} for k,p in profiles.items()}),flush=True)


if __name__=='__main__': main()

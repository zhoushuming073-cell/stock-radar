"""Research-grade PIT policy. Never changes or delegates to the strict gate.

Risk classifications are validation findings. Only evidence available by the
decision session can affect a universe. Missing inputs have three-valued
eligibility; UNKNOWN is never silently filtered out of the population audit.
"""
from __future__ import annotations

from difflib import SequenceMatcher
from functools import lru_cache
import json
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd

from radar.pit.builder import digest
from radar.pit.features import file_hash
from radar.pit.run import verify_dependencies

POLICY = 'pit-research-grade-v1'
LABEL = 'Research-Grade PIT'
GATES = ('Causal integrity', 'Research identity', 'Research membership',
         'Research price', 'Material corporate actions', 'Terminal', 'LEAN Input')
MEMBERSHIP_CHECKS = ('historical_primary', 'historical_secondary', 'future_listing',
                     'disappearance', 'population_size', 'exchange_coverage',
                     'random_sample', 'later_delisted_sample', 'universe_sensitivity')


@lru_cache(maxsize=100000)
def _name(value):
    words = re.findall(r'[a-z0-9]+', str(value).lower())
    noise = {'inc','incorporated','corp','corporation','company','co','ltd','limited',
             'common','stock','stocks','shares','share','ordinary','plc','the'}
    return ' '.join(w for w in words if w not in noise)


@lru_cache(maxsize=100000)
def _same_name(a,b):
    return SequenceMatcher(None,a,b).ratio()>=.72


def classify_identity(record, observations, rules, *, as_of=None, collision=False,
                      event_risk=False, price_continuous=True):
    """No merger of episodes; A is a scoped validation, not permanent class ID.

    `as_of` is mandatory for any selection decision. Omitting it evaluates the
    entire closure for audit only. It must never be used as a historical filter.
    """
    mappings = record['mappings']
    actions=record.get('actions',[])
    if as_of is not None:
        mappings = [m for m in mappings if m['valid_from'][:10] <= as_of]
        observations = [o for o in observations if o['available_on'] <= as_of]
        actions=[a for a in actions if a.get('available_on',a['effective_date'])<=as_of]
    symbols = {m['symbol'] for m in mappings}
    names = {_name(m.get('security_name','')) for m in mappings}
    issuers = {str(o['cik']).zfill(10) for o in observations}
    high, medium = [], []
    if collision: high.append('ticker has multiple observed identity episodes')
    if symbols & set(rules['identity']['high_risk_symbols']): high.append('protected reuse/rename chain')
    if len(issuers)>1: high.append('multiple CIKs')
    if event_risk or any(a['event_type'] not in {'cash_dividend','dividend'} for a in actions):
        high.append('material lifecycle/action evidence')
    for m in mappings:
        description = str(m.get('security_name','')).lower()
        if any(re.search(r'\b'+re.escape(p)+r'\b',description)
               for p in rules['identity']['high_risk_name_patterns']):
            high.append('ADR/share-class/lifecycle ambiguity'); break
    if high:
        return {'level':'C','research_identity_pass':False,'reasons':sorted(set(high)),'as_of':as_of}
    if len(symbols)!=1: medium.append('symbol change or unavailable mapping')
    if len({m['exchange'] for m in mappings})!=1: medium.append('exchange transfer')
    if len(names)!=1 or not all(names): medium.append('name change/missing name')
    if any(m.get('security_type')!='common' or not m.get('eligible') for m in mappings):
        medium.append('historical common classification incomplete')
    if len(observations)<rules['identity']['minimum_dated_issuer_observations'] or len(issuers)!=1:
        medium.append('insufficient dated issuer cross-check')
    elif any(not any(_same_name(_name(o['name']),n) for n in names)
             for o in observations):
        medium.append('issuer/name disagreement')
    if as_of is None and observations:
        first = min(record['membership_sessions'])
        if sum(o['available_on']<=first for o in observations)<rules['identity']['minimum_dated_issuer_observations']:
            medium.append('issuer evidence unavailable at first research decision')
    if not price_continuous: medium.append('unexplained price continuity problem')
    return {'level':'B' if medium else 'A','research_identity_pass':not medium,
            'reasons':medium,'as_of':as_of,'ciks':sorted(issuers)}


def price_anomalies(frame, rules):
    """Raw OHLC only. Split-like jumps are escalation signals, never corrections."""
    if frame.empty: return []
    p = rules['prices']; findings = []
    ordered = frame.sort_values('date')
    duplicate = ordered.date.duplicated(keep=False)
    for row in ordered.loc[duplicate].itertuples():
        findings.append({'date':str(row.date)[:10],'kind':'duplicate_session'})
    values = ordered[['open','high','low','close','volume']].astype(float)
    invalid = (~np.isfinite(values).all(axis=1) | values.low.le(0) | values.volume.lt(0)
               | values.volume.ne(np.floor(values.volume))
               | ~values.open.between(values.low,values.high)
               | ~values.close.between(values.low,values.high))
    for row in ordered.loc[invalid].itertuples():
        findings.append({'date':str(row.date)[:10],'kind':'invalid_ohlcv'})
    ratios = values.open / values.close.shift(1)
    for index in ratios.index[(ratios>p['jump_ratio_high']) | (ratios<p['jump_ratio_low'])]:
        ratio = float(ratios.loc[index])
        near = any(abs(ratio-r)/r<=p['split_ratio_tolerance'] for r in
                   [.01,.02,.025,.05,.1,.125,.2,.25,1/3,.5,2,3,4,5,8,10,20,40,50,100])
        findings.append({'date':str(ordered.loc[index,'date'])[:10],
                         'kind':'split_like_jump' if near else 'price_discontinuity','ratio':ratio})
    vr = values.volume / values.volume.shift(1).replace(0,np.nan)
    for index in vr.index[vr>p['volume_ratio_high']]:
        findings.append({'date':str(ordered.loc[index,'date'])[:10],'kind':'extreme_volume','ratio':float(vr.loc[index])})
    return findings


def core_membership(day, members, bars, calendar, rules):
    """Past-only liquidity ranking, independent of later data and strategy P&L.

    Returns admitted IDs plus unresolved competitors. Even a single unresolved
    competitor can displace a rank; native readiness must bound this effect.
    """
    settings = rules['core']; prior = [d for d in calendar if d<day]
    lookback = prior[-settings['minimum_history_sessions']:]
    ranked, unknown, rejected = [], [], {}
    groups = dict(tuple(bars.loc[bars.date.astype(str).str[:10].isin(lookback)].groupby('security_id')))
    for member in members:
        sid = member['security_id']
        if member.get('listing_date') and member['listing_date'][:10]>day:
            rejected[sid]='future_listing'; continue
        if member.get('security_type')!='common':
            rejected[sid]='not_common'; continue
        if member.get('listing_date') and len([d for d in lookback if d>=member['listing_date'][:10]])<settings['minimum_history_sessions']:
            rejected[sid]='known_short_trading_history'; continue
        group = groups.get(sid)
        if group is None or group.empty:
            unknown.append(sid); continue
        part = group.sort_values('date')
        last = part.iloc[-1]
        # A known price below the floor proves ineligibility despite other gaps.
        if str(last.date)[:10]==prior[-1] and float(last.close)<settings['price_floor']:
            rejected[sid]='known_prior_price_below_floor'; continue
        recent_known=part.loc[part.date.astype(str).str[:10].isin(prior[-settings['dollar_volume_lookback']:])]
        dollars_known=recent_known.close.astype(float)*recent_known.volume.astype(float)
        if (len(dollars_known) and np.isfinite(dollars_known).all() and
                float(dollars_known.min())<settings['minimum_daily_dollar_volume']):
            rejected[sid]='known_insufficient_daily_liquidity';continue
        if (len(recent_known)==settings['dollar_volume_lookback'] and
                float(dollars_known.mean())<settings['minimum_avg_dollar_volume']):
            rejected[sid]='known_insufficient_average_liquidity';continue
        if (len(lookback)<settings['minimum_history_sessions'] or
            len(part)!=len(lookback) or set(part.date.astype(str).str[:10])!=set(lookback)
            or part.date.duplicated().any()):
            unknown.append(sid); continue
        v = part[['open','high','low','close','volume']].astype(float)
        if (not np.isfinite(v).all().all() or (v.low<=0).any() or (v.volume<0).any()
            or not v.open.between(v.low,v.high).all() or not v.close.between(v.low,v.high).all()):
            unknown.append(sid); continue
        recent = part.tail(settings['dollar_volume_lookback'])
        dollars = recent.close.astype(float)*recent.volume.astype(float)
        if (float(dollars.mean())<settings['minimum_avg_dollar_volume'] or
                float(dollars.min())<settings['minimum_daily_dollar_volume']):
            rejected[sid]='known_insufficient_liquidity'; continue
        ranked.append((sid,float(dollars.mean())))
    ranked.sort(key=lambda r:(-r[1],r[0]))
    return {'date':day,'security_ids':[r[0] for r in ranked[:settings['target_size']]],
            'unknown_security_ids':sorted(unknown),'rejected':rejected,
            'eligible_before_cap':len(ranked),'possible_rank_displacement':min(len(unknown),settings['target_size']),
            'causal_cutoff':prior[-1] if prior else None,'definitive':not unknown}


def sensitivity(profiles, rules, *, stage='complete'):
    """Require all metrics, same frozen contract and unknown-population bounds."""
    limits = rules['sensitivity']; comparisons = []; failures = []
    if set(profiles)!={'A','B','C'}:
        return {'status':'NOT_RUN','reason':'all three profiles required','comparisons':[]}
    metrics = {'win_rate':'win_rate_absolute_difference_max','path_success':'path_success_absolute_difference_max',
               'mfe':'mfe_absolute_difference_max','mae':'mae_absolute_difference_max',
               'native_return':'native_return_absolute_difference_max',
               'native_drawdown':'native_drawdown_absolute_difference_max',
               'average_trade':'average_trade_absolute_difference_max',
               'fee_equity_fraction':'fee_equity_fraction_difference_max'}
    if stage=='scanner':
        metrics={k:v for k,v in metrics.items() if k in {'win_rate','path_success','mfe','mae'}}
    elif stage!='complete':
        raise ValueError('unknown sensitivity stage')
    contract = profiles['A'].get('contract_sha256')
    if not contract or any(p.get('contract_sha256')!=contract for p in profiles.values()):
        failures.append('strategy/config/window/execution contract differs')
    if any(p.get('unknown_impact_bounded') is not True for p in profiles.values()):
        failures.append('common missing population/selection impact unbounded')
    for a,b in [('A','B'),('A','C'),('B','C')]:
        left,right = profiles[a],profiles[b]
        ls,rs = set(left.get('candidate_ids',[])),set(right.get('candidate_ids',[]))
        overlap = len(ls&rs)/len(ls|rs) if ls|rs else None
        item={'pair':[a,b],'candidate_counts':[len(ls),len(rs)],'overlap_jaccard':overlap,'differences':{}}
        if overlap is None or overlap<limits['candidate_overlap_jaccard_min']: failures.append(f'{a}/{b}: candidate overlap')
        for metric, threshold in metrics.items():
            values = [left.get(metric),right.get(metric)]
            if any(v is None or not math.isfinite(float(v)) for v in values):
                item['differences'][metric]=None; failures.append(f'{a}/{b}: {metric} not measured'); continue
            delta=abs(values[0]-values[1]);item['differences'][metric]=delta
            if delta>limits[threshold]: failures.append(f'{a}/{b}: {metric} exceeds frozen tolerance')
        if stage=='complete':
            trades=[left.get('trade_count'),right.get('trade_count')]
            if any(v is None for v in trades) or max(trades)==0:
                item['trade_count_relative_difference']=None;failures.append(f'{a}/{b}: trades not measured')
            else:
                relative=abs(trades[0]-trades[1])/max(trades);item['trade_count_relative_difference']=relative
                if relative>limits['trade_count_relative_difference_max']: failures.append(f'{a}/{b}: trade count differs')
        comparisons.append(item)
    return {'status':'FAIL' if failures else 'PASS','stage':stage,'failures':failures,'comparisons':comparisons,
            'interpretation':limits['interpretation']}


def research_readiness(manifest, audit, rules, *, verify=True):
    """Validate evidence-bound findings; never infer research PASS from strict FAIL."""
    if verify: verify_dependencies(manifest)
    if audit.get('policy')!=POLICY or audit.get('dependency_sha256')!=manifest['dependency_sha256']:
        raise ValueError('research audit does not bind this closure')
    if audit.get('rules_sha256')!=digest(rules): raise ValueError('research policy changed')
    body={k:v for k,v in audit.items() if k!='audit_sha256'}
    if audit.get('audit_sha256')!=digest(body): raise ValueError('research audit changed')
    bound=set()
    for item in audit.get('files',[]):
        if verify and file_hash(Path(item['path']))!=item['sha256']: raise ValueError('research evidence changed')
        bound.add(item['sha256'])
    reasons={g:[] for g in GATES}
    for gate in GATES:
        finding=audit.get('gates',{}).get(gate,{})
        hashes=set(finding.get('evidence_hashes',[]))
        if (finding.get('status')!='PASS' or not hashes or not hashes<=bound
                or not finding.get('explanation')):
            reasons[gate].extend(finding.get('reasons') or ['missing or unbound gate evidence'])
    membership=audit.get('membership',{})
    for key in MEMBERSHIP_CHECKS:
        finding=membership.get('checks',{}).get(key,{})
        hashes=set(finding.get('evidence_hashes',[]))
        if finding.get('status')!='PASS' or not hashes or not hashes<=bound:
            reasons['Research membership'].append(key+': not validated')
    # Quantitative mandatory vetoes, independent of claimed gate statuses.
    scope=audit.get('scope',{})
    actual_missing=sum(len(r['missing_sessions']) for r in manifest['dependencies']+manifest['benchmarks'])
    if scope.get('missing_prices')!=actual_missing:
        reasons['Research price'].append('audit missing count differs from frozen execution closure')
    identity_decisions=audit.get('identity_decisions',{})
    ordinary=audit.get('ordinary_dividend',{})
    cash_bound=ordinary.get('portfolio_return_bound')
    ordinary_bound_ok=(isinstance(cash_bound,(int,float)) and math.isfinite(cash_bound)
        and 0<=cash_bound<=rules['ordinary_dividend']['maximum_portfolio_return_bound'])
    ordinary_ids=set(ordinary.get('ordinary_event_ids',[]))
    eligible_ordinary={a['event_id'] for row in manifest['dependencies'] for a in row.get('actions',[])
        if a.get('event_type')=='dividend' and a.get('confidence')=='verified'
        and a.get('review',{}).get('ordinary_cash_dividend') is True
        and a.get('source',{}).get('raw_sha256') in bound}
    if not ordinary_ids<=eligible_ordinary:
        reasons['Material corporate actions'].append('dividend exception contains nonordinary/unverified material events')
    for row in manifest['dependencies']+manifest['benchmarks']:
        if 'security_id' in row:
            strict_identity=all(m.get('resolution_status')=='verified' and m.get('classification_confidence')=='verified'
                and m.get('issuer_id') and m.get('share_class') and m.get('identity_evidence_hash') in
                {v['sha256'] for v in manifest['files'].values()} for m in row['mappings'])
            decision=identity_decisions.get(row['security_id'],{})
            observed=decision.get('observations',[])
            recalculated=classify_identity(row,observed,rules,collision=decision.get('collision',False),
                event_risk=decision.get('event_risk',False),price_continuous=decision.get('price_continuous',False))
            if not strict_identity and (decision.get('level')!='A' or not recalculated['research_identity_pass']):
                reasons['Research identity'].append(row['security_id']+': research identity evidence not A/strict verified')
        if not {s['adjustment'] for s in row['price_sources']}<={'raw','none','unadjusted'}:
            reasons['Research price'].append(row.get('security_id',row.get('symbol'))+': execution inputs are adjusted')
        if row.get('price_mapping_mismatch'):
            reasons['Research identity'].append(row['security_id']+': dated price mapping mismatch')
        for action in row.get('actions',[]):
            if (ordinary_bound_ok and action['event_id'] in ordinary_ids and action.get('event_type')=='dividend'
                    and action.get('confidence')=='verified' and action.get('review',{}).get('ordinary_cash_dividend') is True
                    and action.get('source',{}).get('raw_sha256') in bound):
                continue
            if action.get('confidence')!='verified' or action.get('handling_mode')=='blocked':
                from radar.pit.actions import TERMINALS
                reasons['Terminal' if action.get('event_type') in TERMINALS else
                        'Material corporate actions'].append(action['event_id']+': strict material handling incomplete')
    for key,gate in [('unresolved_identities','Research identity'),('missing_prices','Research price'),
                     ('unhandled_material_actions','Material corporate actions'),('unhandled_terminals','Terminal'),
                     ('unbounded_unknown_members','Research membership')]:
        if key not in scope or scope[key]!=0: reasons[gate].append(key+': unresolved or unmeasured')
    if audit.get('hard_failures'): reasons['Causal integrity'].extend(audit['hard_failures'])
    if audit.get('causal_verified') is not True: reasons['Causal integrity'].append('causal audit not complete')
    # Preflight uses observed Scanner sensitivity. Native portfolio sensitivity
    # is a post-execution acceptance check, avoiding a self-blocking dependency.
    measured=sensitivity(audit.get('sensitivity_profiles',{}),rules,stage='scanner')
    if measured['status']!='PASS': reasons['Research membership'].append('universe sensitivity not PASS')
    dividend=audit.get('ordinary_dividend',{})
    bound_value=dividend.get('portfolio_return_bound')
    if (bound_value is None or not math.isfinite(float(bound_value)) or bound_value<0
            or bound_value>rules['ordinary_dividend']['maximum_portfolio_return_bound']):
        reasons['Material corporate actions'].append('ordinary dividend impact not bounded within tolerance')
    if any(reasons[g] for g in GATES if g!='LEAN Input'):
        reasons['LEAN Input'].append('research upstream gates incomplete')
    scores={g:'FAIL' if reasons[g] else 'PASS' for g in GATES}
    ready=all(v=='PASS' for v in scores.values())
    return {'scope':'run','policy':POLICY,'quality_tier':'research-grade','label':LABEL,
            'dependency_sha256':manifest['dependency_sha256'],'audit_sha256':audit['audit_sha256'],
            'research_pit_ready':ready,'preflight_ready':ready,'formal_pit_ready':False,
            'research_validity':'research_grade_pit' if ready else 'research_grade_pit_blocked',
            'scorecard':{**scores,'LEAN Native Execution':'NOT_RUN','Result Reconciliation':'NOT_RUN'},
            'reasons_by_gate':reasons,'scope_counts':scope,'population_scopes':audit.get('scope_counts',{}),
            'sensitivity':measured,'fallback':'forbidden'}


def require_research_ready(manifest,audit,rules):
    result=research_readiness(manifest,audit,rules)
    if not result['preflight_ready']:
        raise ValueError('Research-Grade PIT LEAN BLOCKED: '+json.dumps({
            k:len(v) for k,v in result['reasons_by_gate'].items() if v},sort_keys=True))
    return result


def load_research_acceptance(audit_reference,rules_reference):
    """Explicit queue-time byte locks; never use a newer local default audit."""
    result=[]
    for reference in (audit_reference,rules_reference):
        if not reference or not reference.get('path') or not reference.get('sha256'):
            raise ValueError('Research-Grade PIT requires frozen audit/rules; no fallback')
        path=Path(reference['path'])
        if file_hash(path)!=reference['sha256']: raise ValueError('queued research acceptance changed')
        result.append(json.loads(path.read_text(encoding='utf-8')))
    return tuple(result)


def local_research_readiness(root):
    """Read-only API entry; absent artifacts stay BLOCKED, never Current Snapshot."""
    root=Path(root); path=root/'data/pit/research-grade/audit.json'
    if not path.exists():
        return {'policy':POLICY,'label':LABEL,'quality_tier':'research-grade',
                'preflight_ready':False,'research_pit_ready':False,'formal_pit_ready':False,
                'research_validity':'research_grade_pit_blocked','fallback':'forbidden',
                'scorecard':{g:'FAIL' for g in GATES},'reason':'research audit unavailable'}
    audit=json.loads(path.read_text(encoding='utf-8'))
    rules=json.loads((root/'config/pit_research_grade_rules.json').read_text(encoding='utf-8'))
    ref=audit['dependency_reference']
    from radar.pit.run import load_dependency
    manifest=load_dependency(ref)
    return research_readiness(manifest,audit,rules)

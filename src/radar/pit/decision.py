"""Decision-scoped PIT evidence; interval scenarios never manufacture market bars."""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
import math
import re

from radar.pit.research import classify_identity


def candidate_identity(record, observations, risk, rules):
    """Re-audit candidates only; explicit stable Class A common is not ambiguity.

    This requires repeated dated class descriptions plus two dated issuer checks.
    It does not resolve ADR/common ambiguity, issuer collisions or reuse. Price
    and action findings remain separate vetoes and cannot be cleared here.
    """
    if risk.get('strict_verified'):
        return {'pass':True,'level':'strict','method':'existing strict identity evidence'}
    settings=deepcopy(rules)
    descriptions=[m.get('security_name','') for m in record['mappings']]
    classes=[re.search(r'\bclass\s+([a-z0-9]+)\s+common\s+(?:stock|shares)\b',n,re.I) for n in descriptions]
    repeated_class=(classes and all(classes) and len({m.group(1).lower() for m in classes})==1
                    and all(m.get('first_source_commit') and m.get('last_source_commit')
                            and m['first_source_commit']!=m['last_source_commit'] for m in record['mappings']))
    if repeated_class:
        settings['identity']['high_risk_name_patterns']=[p for p in settings['identity']['high_risk_name_patterns'] if p!='class']
    issuer=classify_identity(record,observations,settings,
        collision='ticker has multiple observed identity episodes' in risk['reasons'],
        event_risk=bool(risk.get('lifecycle_disappearance') or record.get('actions')),price_continuous=True)
    return {'pass':issuer['research_identity_pass'],'level':issuer['level'],'reasons':issuer['reasons'],
            'method':'repeated historical explicit class/common description + dated stable issuer' if repeated_class else
                     'dated stable issuer/common description; event/price gates separate'}


def competitor_interval(sid, recent, known_ranked, *, target=1000, window=20,
                        history_complete=False, identity_resolved=False):
    """A complete dated window gives an exact rank even with earlier gaps.

    Unknown volume has no finite upper bound. An empirical maximum is a stress
    assumption, not evidence that a missing failed security could not compete.
    known_ranked contains the fully eligible population before the cap.
    """
    values = list(recent)
    if len(values) != window or any(v is None or not math.isfinite(v) or v < 0 for v in values):
        return {'security_id': sid, 'category': 'unbounded_competitor',
                'dollar_volume_lower': sum(v for v in values if v is not None and math.isfinite(v) and v >= 0)/window,
                'dollar_volume_upper': None, 'best_rank': 1, 'eligible_proven': False}
    mean = math.fsum(values)/window
    better = sum(d > mean or (d == mean and other < sid) for other, d in known_ranked)
    rank = better + 1
    category = ('core_non_competitor' if rank > target else
                'resolved_eligible_competitor' if history_complete and identity_resolved else
                'borderline_competitor' if rank >= target - 100 else 'likely_in_competitor')
    return {'security_id': sid, 'category': category, 'dollar_volume_lower': mean,
            'dollar_volume_upper': mean, 'best_rank': rank,
            'eligible_proven': history_complete and identity_resolved}


def resolved_core(known_ranked, competitors, *, target=1000):
    """D changes only on actual resolved eligibility, never on an imputed bar."""
    ranking = dict(known_ranked)
    for item in competitors:
        if item.get('eligible_proven') and item.get('dollar_volume_upper') is not None:
            ranking[item['security_id']] = item['dollar_volume_upper']
    return [sid for sid, _ in sorted(ranking.items(), key=lambda r: (-r[1], r[0]))[:target]]


def daily_top(rows, days, k=3):
    grouped = defaultdict(list)
    for row in rows:
        if row.get('selected'):
            grouped[row['signal_date']].append(row)
    return {day: [r['security_id'] for r in sorted(grouped[day], key=lambda r:(r['rank'],r['symbol']))[:k]]
            for day in days}


def top_stability(left, right):
    """Slot coverage and identical empty days are reported separately."""
    if set(left) != set(right):
        raise ValueError('decision calendars differ')
    daily = []
    for day in sorted(left):
        a, b = left[day], right[day]
        denominator = max(len(a), len(b))
        overlap = len(set(a) & set(b))
        daily.append({'date': day, 'left': a, 'right': b, 'overlap': overlap,
                      'slots': denominator, 'identical_set': set(a)==set(b),
                      'identical_order': a==b,
                      'slot_overlap': overlap/denominator if denominator else None})
    total = sum(d['slots'] for d in daily)
    return {'slot_overlap': sum(d['overlap'] for d in daily)/total if total else None,
            'identical_day_fraction': sum(d['identical_set'] for d in daily)/len(daily) if daily else None,
            'identical_order_fraction': sum(d['identical_order'] for d in daily)/len(daily) if daily else None,
            'active_days': sum(d['slots'] > 0 for d in daily),
            'empty_both_days': sum(d['slots'] == 0 for d in daily), 'days': daily}


def missingness_envelope(top, unknown_by_day, *, k=3, observed_outcomes=None):
    """Conservative logical selection/outcome bounds, not fictional returns.

    Unknown feature history can change cross-sectional elasticity of every
    existing member. Even one competitor can therefore change all top-k slots.
    A score-only injection understates this population-rank coupling.
    """
    daily=[]
    for day, chosen in sorted(top.items()):
        n=len(unknown_by_day.get(day, []))
        daily.append({'date':day,'true_competitors':n,
                      'best_changed_existing_slots':0,
                      'worst_changed_slots':k if n else 0,
                      'worst_changed_existing_slots':len(chosen) if n else 0,
                      'new_candidate_injection_upper':n,
                      'independent_score_injection_displacement':min(n,len(chosen)),
                      'excluded_unresolved':False,
                      'ranking_scope':'cross-sectional percentile may change existing scores' if n else 'unchanged'})
    uncertain=sum(d['true_competitors']>0 for d in daily)
    outcomes=observed_outcomes or {}
    return {'status':'FAIL' if uncertain else 'PASS', 'days':daily,
            'uncertain_days':uncertain,'maximum_daily_changed_slots':max((d['worst_changed_slots'] for d in daily),default=0),
            'sum_changed_slots_upper':sum(d['worst_changed_slots'] for d in daily),
            'scenario_best':{'changed_existing_slots':0,'interpretation':'favorable eligibility/features, not established fact'},
            'scenario_worst':{'hit_rate_interval':[0,1] if uncertain else outcomes.get('hit_rate_interval'),
                              'path_success_interval':[0,1] if uncertain else outcomes.get('path_success_interval'),
                              'interpretation':'logical envelope, unknown future outcomes; no imputed OHLCV'},
            'scenario_excluded':{'only_proven_noncompetitors':True,'unresolved_removed':0},
            'note':'aggregate worst upper envelope need not be simultaneously attainable; it cannot certify a small bound'}


def scoped_readiness(findings, rules):
    """No gate depends on unrelated full-market blocker counts."""
    limits=rules['release']; reasons={g:[] for g in
        ['Causal integrity','Research identity','Research membership','Research price',
         'Material corporate actions','Terminal','LEAN Input']}
    require=lambda gate,condition,message: reasons[gate].append(message) if not condition else None
    require('Causal integrity',findings.get('frozen_before_analysis') is True,'decision rules not frozen before analysis')
    require('Causal integrity',findings.get('causal_selection_verified') is True,'causal selection/input scope unverified')
    require('Causal integrity',findings.get('decision_uncertainty_bounded') is True,'unresolved inputs can still change historical decisions')
    require('Research membership',findings.get('membership_crosschecks_verified') is True,'historical membership crosschecks incomplete')
    require('Research membership',findings.get('maximum_daily_true_competitors',math.inf)<=limits['maximum_daily_true_competitors'], 'effective Core competitors exceed frozen budget')
    require('Research membership',findings.get('top3_slot_overlap',0)>=limits['minimum_top3_slot_overlap'],'C/D Top3 overlap below frozen threshold')
    require('Research membership',findings.get('identical_top3_days',0)>=limits['minimum_identical_top3_days'],'C/D identical decision days below frozen threshold')
    require('Research membership',findings.get('maximum_unknown_changed_top3_slots',math.inf)<=limits['maximum_unknown_changed_top3_slots'],'remaining missingness can change Top3')
    require('Research membership',findings.get('outcomes_stable') is True,'decision outcome sensitivity incomplete or unstable')
    for gate,key,limit in [('Research identity','candidate_identity_unresolved','maximum_candidate_identity_unresolved'),
                           ('Research price','candidate_execution_gaps','maximum_candidate_execution_gaps'),
                           ('Material corporate actions','candidate_material_unresolved','maximum_candidate_material_unresolved'),
                           ('Terminal','known_split_terminal_unresolved','maximum_known_split_terminal_unresolved')]:
        require(gate, findings.get(key,math.inf)<=limits[limit],key+' exceeds frozen threshold')
    require('Research price',findings.get('feature_ranking_scope_complete') is True,'ranking feature/benchmark scope incomplete')
    cash=findings.get('ordinary_dividend_return_bound')
    require('Material corporate actions',isinstance(cash,(int,float)) and math.isfinite(cash) and 0<=cash<=limits['ordinary_dividend_return_bound'], 'ordinary dividend effect not reliably bounded')
    require('LEAN Input',findings.get('native_input_verified') is True,'real frozen native inputs not verified')
    if any(reasons[g] for g in reasons if g!='LEAN Input'):
        reasons['LEAN Input'].append('decision-scoped upstream gates incomplete')
    scores={g:'FAIL' if r else 'PASS' for g,r in reasons.items()}
    return {'policy':rules['policy'],'quality_tier':'research-grade','label':'Research-Grade PIT',
            'ready':all(v=='PASS' for v in scores.values()),'scorecard':scores,'reasons':reasons,
            'native_execution':'NOT_RUN','reconciliation':'NOT_RUN','fallback':'forbidden'}


def require_scoped_ready(findings,rules):
    result=scoped_readiness(findings,rules)
    if not result['ready']:
        raise ValueError('Research-Grade PIT decision scope BLOCKED; no Current fallback')
    return result

"""Evidence types for focused resolution and score-only stress experiments."""
import math


def holding_mapping_gaps(mappings, sessions):
    """An intermediate mapping end is not an economic terminal event."""
    return [d for d in sessions if not any(m['valid_from'][:10]<=d<=(m.get('valid_to') or '9999')[:10] for m in mappings)]


def short_history_proof(day, fact, calendar, security_name):
    if fact['available_on']>day or fact['issuer_name'].lower() not in security_name.lower():
        return None
    history=[d for d in calendar if fact['first_trading']<=d<day]
    if len(history)>=126:return None
    return {'status':'core_non_competitor','reason':'known new listed class has fewer than 126 possible past sessions',
            'maximum_possible_sessions':len(history),'source_sha256':fact['source_sha256'],
            'first_trading':fact['first_trading'],'available_on':fact['available_on']}


def executable_raw_bar(row):
    numbers=[row.get(k) for k in ['open','high','low','close','volume']]
    if any(v is None or not math.isfinite(float(v)) for v in numbers):return False
    op,hi,lo,close,volume=map(float,numbers)
    return lo>0 and lo<=op<=hi and lo<=close<=hi and volume>0 and row.get('adjustment')=='raw'


def score_stress(rows, unknown_by_day, core_by_day, *, top_k=3, upper_score=100.):
    """A selection witness, not realizable OHLCV or a portfolio simulator.

    Worst adds score-upper-bound eligible competitors and removes the bottom
    observed Core liquidity members to preserve the cap. Existing scores are
    held fixed in this witness; the wider eligibility envelope is separate.
    Unknown outcomes remain intervals. No fabricated outcome rate is reported.
    """
    grouped={day:[] for day in core_by_day}
    for r in rows:
        if r.get('selected'):grouped[r['signal_date']].append(r)
    daily=[]
    for day,core in core_by_day.items():
        observed=sorted(grouped[day],key=lambda r:(-r['strategy_score'],r['symbol']))
        best=[r['security_id'] for r in observed[:top_k]]
        unknown=sorted(unknown_by_day.get(day,[]))
        # Conservative admissible membership envelope. This does not assert
        # that missing features jointly achieve upper_score for these issuers.
        retained=set(core[:max(0,len(core)-len(unknown))])
        choices=[(r['security_id'],float(r['strategy_score']),r['symbol']) for r in observed if r['security_id'] in retained]
        choices.extend((sid,upper_score,'~'+sid) for sid in unknown)
        choices.sort(key=lambda r:(-r[1],r[2]))
        worst=[r[0] for r in choices[:top_k]]
        daily.append({'date':day,'best':best,'excluded':best,'worst':worst,
            'changed_observed_slots':len(set(best)-set(worst)),
            'changed_selection_slots':max(len(best),len(worst))-len(set(best)&set(worst)),
            'unknown_competitors':len(unknown),
            'candidate_count_best':len(observed),'candidate_count_worst_score_witness':len(choices),
            'upper_score':upper_score,'unknown_outcome_interval':[0,1] if unknown else None})
    return {'days':daily,'changed_days':sum(d['best']!=d['worst'] for d in daily),
            'maximum_changed_slots':max((d['changed_selection_slots'] for d in daily),default=0),
            'sum_changed_observed_slots':sum(d['changed_observed_slots'] for d in daily),
            'sum_changed_selection_slots':sum(d['changed_selection_slots'] for d in daily),
            'claim':'score interval stress witness; not historical trades, prices or jointly proven attainable histories',
            'excluded_rule':'only proven noncompetitors removed; unresolved retained in the uncertainty set'}

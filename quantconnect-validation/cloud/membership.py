from datetime import datetime
import hashlib
import pandas as pd
from qc_core import core_membership
from qc_protocol import digest, historical_join, membership_summary, normalize_cik, normalize_class
from qc_data_adapter import raw_frames

CLASS_CODES = ['QC Confirms Out', 'QC Confirms In', 'QC Borderline',
               'QC Identity / Lifecycle Conflict', 'QC Coverage Unknown']
REASONS = ['eligible', 'known_rule_failure', 'rank_beyond_cutoff', 'boundary',
           'insufficient_qc_history', 'qc_scope_or_data_missing', 'identity_conflict']


def population_from_objects(objects, day):
    result = []
    for f in objects:
        ref = f.security_reference
        kind = str(ref.security_type)
        is_common = kind == 'ST00000001' and not ref.is_depositary_receipt
        description = normalize_class(ref.share_class_description)
        ipo = ref.ipo_date
        result.append({'symbol_object': f.symbol, 'sid': str(f.symbol.id), 'ticker': f.symbol.value,
            'as_of': day, 'cik': normalize_cik(f.company_reference.cik),
            'class': description or ('COMMON' if is_common else ''),
            'security_type': 'common' if is_common else ('unknown' if not kind else 'other'),
            'listing_date': str(ipo.date()) if ipo.year > 1900 else None})
    if len({p['sid'] for p in result}) != len(result):
        raise ValueError('Duplicate historical fundamental SID')
    return result


def independent_core(algorithm, population, day, rules, warmup_start):
    # NO local membership, identity classification or OHLCV argument.
    spy = algorithm._benchmarks['SPY']
    symbols = [p['symbol_object'] for p in population]
    if spy not in symbols:
        symbols.append(spy)
    frames = raw_frames(algorithm, symbols, warmup_start, datetime.fromisoformat(day))
    calendar = [str(d.date()) for d in frames[str(spy.id)].index]
    if not calendar:
        raise ValueError('QC prior-session calendar unavailable')
    members = [{'security_id': p['sid'], 'security_type': p['security_type'],
                'listing_date': p['listing_date']} for p in population]
    bars = pd.concat([frame.reset_index().assign(security_id=sid) for sid, frame in frames.items()],
                     ignore_index=True)
    result = core_membership(day, members, bars, calendar, rules)
    # Missing security-type metadata is epistemically unknown, never known not-common.
    type_unknown = [p['sid'] for p in population if p['security_type'] == 'unknown']
    result['unknown_security_ids'] = sorted(set(result['unknown_security_ids']) | set(type_unknown))
    for sid in type_unknown:
        result['rejected'].pop(sid, None)
    result['definitive'] = not result['unknown_security_ids']
    # Re-run the frozen ranking without a cap to locate the 950..1050 boundary.
    expanded_rules = {**rules, 'core': {**rules['core'], 'target_size': len(members)}}
    ranking = core_membership(day, members, bars, calendar, expanded_rules)['security_ids']
    result['rank'] = {sid: n + 1 for n, sid in enumerate(ranking)}
    result['population_type_unknown'] = len(type_unknown)
    result['assessment'] = {}
    for member in members:
        sid = member['security_id']
        frame = frames[sid]
        recent = frame.loc[frame.index.isin(pd.to_datetime(calendar[-rules['core']['dollar_volume_lookback']:]))]
        dollars = recent.close * recent.volume
        history_n = rules['core']['minimum_history_sessions']
        enough = len(frame.tail(history_n)) == history_n and list(frame.tail(history_n).index) == list(pd.to_datetime(calendar[-history_n:]))
        price = (not frame.empty and str(frame.index[-1].date()) == calendar[-1] and
                 float(frame.close.iloc[-1]) >= rules['core']['price_floor'])
        average = len(recent) == rules['core']['dollar_volume_lookback'] and float(dollars.mean()) >= rules['core']['minimum_avg_dollar_volume']
        daily = len(dollars) > 0 and float(dollars.min()) >= rules['core']['minimum_daily_dollar_volume']
        result['assessment'][sid] = (1 | (2 if enough else 0) | (4 if price else 0) |
                                      (8 if average else 0) | (16 if daily else 0) |
                                      (32 if sid in result['security_ids'] else 0) |
                                      (64 if 950 <= result['rank'].get(sid, 0) <= 1050 else 0))
    return result


def compare_membership(population, qc_core, local, day):
    qc_ids = set(qc_core['security_ids'])
    matched_local, matched_qc, unresolved, bridge = [], [], [], {}
    for index in local['core']:
        q, reason = historical_join(local['identities'][index], population, day)
        if q is None:
            unresolved.append(index)
        else:
            bridge[index] = q['sid']
    counts = {}
    for sid in bridge.values():
        counts[sid] = counts.get(sid, 0) + 1
    for index, sid in list(bridge.items()):
        if counts[sid] != 1:
            unresolved.append(index)
            del bridge[index]
        elif sid in qc_ids:
            matched_local.append(index)
            matched_qc.append(sid)
    record = {'type': 'membership', 'date': day,
              **membership_summary(len(local['core']), len(qc_ids), matched_local, matched_qc, len(unresolved)),
              'qc_unknown_count': len(qc_core['unknown_security_ids']),
              'population_type_unknown': qc_core['population_type_unknown'],
              'qc_membership_hash': digest(sorted(qc_ids)),
              'identity_unresolved_hash': digest(unresolved), 'identity_unresolved_sample': unresolved[:25],
              'local_only_hash': digest(sorted(set(local['core']) - set(matched_local))),
              'local_only_sample': sorted(set(local['core']) - set(matched_local))[:25],
              'qc_only_hash': digest(sorted(qc_ids - set(matched_qc))),
              'qc_only_sample': sorted(qc_ids - set(matched_qc))[:25],
              'unknown_competitors': [], 'boundary_mismatch_count': 0,
              'execution_identity_references': [],
              'details_complete': not unresolved and len(qc_ids - set(matched_qc)) <= 25}
    for index in local.get('execution_identity_requests', []):
        q, reason = historical_join(local['identities'][index], population, day)
        if q is not None:
            record['execution_identity_references'].append({'index': index,
                **{k: q[k] for k in ['sid', 'ticker', 'as_of', 'cik', 'class']}, 'join_method': reason})
    for index in local['unknown']:
        q, reason = historical_join(local['identities'][index], population, day)
        if q is None:
            absent = reason == 'qc_scope_or_data_missing'
            code, why = (4, 5) if absent else (3, 6)
            rank = None
        else:
            sid = q['sid']; rank = qc_core['rank'].get(sid)
            if sid in qc_core['unknown_security_ids']:
                code, why = 4, 4
            elif sid in qc_core['rejected']:
                code, why = 0, 1
            elif rank is None:
                code, why = 4, 4
            elif 950 <= rank <= 1050:
                code, why = 2, 3
            elif sid in qc_ids:
                # Unmeasured QC competitors could still displace a known rank.
                # Every unmeasured QC competitor may outrank this name. A known
                # rank is nevertheless IN if even that worst rank fits the cap.
                code, why = ((1, 0) if rank + len(qc_core['unknown_security_ids']) <= len(qc_core['security_ids'])
                             else (4, 4))
            else:
                code, why = 0, 2
        # Small indices reference immutable local UID dictionary, not ticker strings.
        record['unknown_competitors'].append([index, code, why, rank,
            qc_core['assessment'].get(q['sid']) if q is not None else None])
        if code == 2:
            record['boundary_mismatch_count'] += 1
    record['qc_rank_uncertainty'] = len(qc_core['unknown_security_ids'])
    return record, bridge


def membership_details(population, qc_core, local, day, bucket):
    def selected(identity):
        return int(hashlib.sha256(identity.encode()).hexdigest(), 16) % 32 == bucket
    rows, matched = [], set()
    for index, identity in local['identities'].items():
        q, reason = historical_join(identity, population, day)
        if q is not None:
            matched.add(q['sid'])
        if selected(identity['uid']) and (q is None or q['sid'] not in qc_core['security_ids']):
            tickers = {m['ticker'] for m in identity['mappings']
                       if m['from'] <= day <= (m.get('to') or '9999-12-31')}
            references = [{k: p[k] for k in ['sid', 'ticker', 'as_of', 'cik', 'class', 'listing_date']}
                          for p in population if p['ticker'] in tickers]
            rows.append({'local_index': index, 'qc_sid': q['sid'] if q else None, 'reason': reason,
                'core_rule_rejection': qc_core['rejected'].get(q['sid']) if q else None,
                'assessment_flags': qc_core['assessment'].get(q['sid']) if q else None,
                'qc_identity_candidates': references})
    qc_only = sorted(sid for sid in qc_core['security_ids'] if sid not in matched and selected(sid))
    return {'type': 'membership_details', 'date': day, 'bucket': bucket, 'buckets': 32,
            'local_conflicts': rows, 'qc_only': qc_only, 'qc_membership_hash': digest(sorted(qc_core['security_ids']))}

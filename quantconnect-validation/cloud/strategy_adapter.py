"""Data transport around source-generated features/plugin; no strategy formulas."""
import pandas as pd
from qc_causal_features import causal_identity_features
from qc_elasticity import ElasticityConfig
from qc_scoring import ResearchConfig, score_elasticity
from qc_adapter import evaluate_selection
from qc_plugin import PLUGIN
from qc_data_adapter import raw_frames, split_actions
from qc_protocol import digest, historical_join


def qc_candidates(algorithm, population, core, day, inputs):
    symbols = [p['symbol_object'] for p in population if p['security_type'] == 'common']
    for s in algorithm._benchmarks.values():
        if s not in symbols:
            symbols.append(s)
    frames = raw_frames(algorithm, symbols, inputs['feature_start'], algorithm.time)
    spy = frames[str(algorithm._benchmarks['SPY'].id)].close
    qqq = frames[str(algorithm._benchmarks['QQQ'].id)].close
    cfg = ResearchConfig(**inputs['feature_config'])
    ecfg = ElasticityConfig(**inputs['elasticity_config'])
    rows = []
    for p in population:
        sid = p['sid']
        if p['security_type'] != 'common' or sid not in frames or frames[sid].empty:
            continue
        raw = frames[sid].reindex(spy.index)
        if pd.Timestamp(day) not in raw.index or pd.isna(raw.loc[day, 'close']):
            continue
        actions = split_actions(algorithm, p['symbol_object'], inputs['feature_start'], algorithm.time)
        feature = causal_identity_features(raw, spy, qqq, ecfg, cfg, actions=actions, security_id=sid)
        row = feature.loc[pd.Timestamp(day)].to_dict()
        if row.get('tradability_pass') is not True and row.get('tradability_pass') != True:
            continue
        row.update({'date': pd.Timestamp(day), 'symbol': p['ticker'], 'security_name': p['ticker'],
                    'sid': sid, 'close': float(raw.loc[day, 'close'])})
        rows.append(row)
    if not rows:
        raise ValueError('QC causal feature cohort unavailable; empty is not agreement')
    # Elasticity ranks over the whole historical tradable common cohort BEFORE Core restriction.
    daily = score_elasticity(pd.DataFrame(rows), cfg)
    daily = daily.loc[daily.sid.isin(core['security_ids'])].copy()
    ranked, selected = evaluate_selection(PLUGIN, inputs['strategy'], daily)
    sid_by_ticker = dict(zip(daily.symbol, daily.sid))
    if daily.symbol.duplicated().any():
        raise ValueError('Historical ticker ambiguity in plugin data transport')
    result = [{'sid': sid_by_ticker[r.symbol], 'ticker': r.symbol, 'rank': int(r.rank),
               'score': float(r.strategy_score), 'selected': bool(r.selected)}
              for r in ranked.itertuples(index=False)]
    return result, len(rows)


def compare_candidates(qc, population, local, day, cohort_count):
    reverse = {}
    for index in local['identities']:
        q, _ = historical_join(local['identities'][index], population, day)
        if q is not None:
            reverse.setdefault(q['sid'], []).append(index)
    # Different observed local episodes mapping to one QC SID remain conflicts.
    mapped = {sid: ids[0] for sid, ids in reverse.items() if len(ids) == 1}
    chosen = [r for r in qc if r['selected']]
    record = {'type': 'candidates', 'date': day, 'qc_eligible_count': len(qc),
              'qc_selected_count': len(chosen), 'local_eligible_count': len(local['candidates']),
              'local_selected_count': sum(r['selected'] for r in local['candidates']),
              'qc_feature_cohort_count': cohort_count, 'qc_candidate_hash': digest(qc),
              'identity_unresolved': sum(r['sid'] not in mapped for r in chosen),
              'qc_selected': [[mapped.get(r['sid']), r['sid'], r['rank'], r['score']] for r in chosen],
              'top3': [], 'top5': [], 'rank_mismatches': []}
    for k in (3, 5):
        left = [r['index'] for r in local['candidates'] if r['selected']][:k]
        right = [mapped.get(r['sid']) for r in chosen[:k]]
        common = len(set(left) & (set(right) - {None}))
        record['top' + str(k)] = {'local': left, 'qc': right, 'intersection': common,
             'slots': max(len(left), len(right)), 'identical_order': left == right and None not in right}
    local_rank = {r['index']: r['rank'] for r in local['candidates']}
    record['rank_mismatches'] = [[mapped[r['sid']], local_rank.get(mapped[r['sid']]), r['rank']]
                               for r in qc if r['sid'] in mapped and local_rank.get(mapped[r['sid']]) != r['rank']]
    return record

"""Inspectable, deterministic quality reports; missing prices remain denominators."""
from __future__ import annotations

from collections import Counter
import json
import hashlib
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from radar.pit.builder import digest
from radar.pit.trust import episode_candidates

LEAN_GATES = ["signal_identity_unambiguous", "execution_bars_identity_verified",
              "symbol_maps_verified", "split_factors_verified", "position_lifecycle_complete",
              "delisting_events_complete", "terminal_economics_supported", "provenance_complete",
              "real_golden_cases_validated", "native_result_reconciliation"]


def local_scorecard(master, root: Path) -> dict:
    """Serve the offline population audit only when its content binding is current."""
    path = Path(root) / 'data/pit/reports' / master.manifest['source_version'] / 'coverage-v2.json'
    if path.is_file():
        try:
            report = json.loads(path.read_text(encoding='utf-8'))
            content = {k:v for k,v in report.items() if k != 'semantic_sha256'}
            if (report['master_version'] == master.manifest['source_version']
                    and report['fingerprint'] == master.fingerprint
                    and report['semantic_sha256'] == digest(content)
                    and report['reporter_code_sha256'] == hashlib.sha256(Path(__file__).read_bytes()).hexdigest()):
                return {**report['scorecard'], 'coverage_audit_sha256':report['semantic_sha256'],
                        'coverage_calendar_start':report['calendar_start'],
                        'coverage_calendar_end':report['calendar_end']}
        except (OSError, ValueError, KeyError):
            pass
    return {**scorecard(master), 'coverage_audit_status':'unavailable or stale; rerun offline audit'}


def scorecard(master, coverage: dict | None = None, events: list[dict] | None = None) -> dict:
    f = master.frame
    verified = int(f.get("resolution_status", pd.Series("unresolved", index=f.index)).eq("verified").sum())
    unknown = int(f.security_type.eq("unknown").sum())
    classification_verified = int(f.get("classification_confidence", pd.Series("", index=f.index)).eq("verified").sum())
    event_rows = events or []
    report = {"Membership": {"status": "PARTIAL" if master.reconstructed else "PASS",
                  "mapping_intervals": len(f), "source_gap_windows": len(master.manifest.get("source_gaps", [])),
                  "source_attested_complete": not master.reconstructed},
        "Identity": {"status": "PASS" if verified == len(f) else "PARTIAL" if verified else "FAIL",
                     "verified_intervals": verified, "unresolved_intervals": len(f)-verified,
                     "unresolved_ratio": (len(f)-verified)/len(f)},
        "Classification": {"status": "PASS" if unknown == 0 and classification_verified == len(f) else "PARTIAL",
                           "verified_intervals": classification_verified, "unknown_intervals": unknown,
                           "unknown_ratio": unknown/len(f), "unknown_eligible": int((f.eligible & f.security_type.eq('unknown')).sum())},
        "Event": {"status": "PARTIAL" if event_rows or f.listing_date.notna().any() or f.delisting_date.notna().any() else "FAIL", "verified_event_records": len(event_rows) if events is not None else None,
                  "listing_dates_known_intervals": int(f.listing_date.notna().sum()),
                  "delisting_dates_known_intervals": int(f.delisting_date.notna().sum()),
                  "types": dict(Counter(e["event_type"] for e in event_rows))},
        "Price": {"status": "PARTIAL" if master.feature_store else "FAIL", **(coverage or {}),
                  "feature_store_counts": (master.feature_store or {}).get('counts'),
                  "identity_certified_all_series": False},
        "CorporateAction": {"status": "FAIL", "validated_general_factor_pipeline": False,
                            "terminal_economic_models_enabled": 0, "documented_split_events": sum(e['event_type']=='split' for e in event_rows)}}
    return {"dimensions": report, "lean_pit_execution_ready": False,
            "lean_minimum_gates": {key: {"status": "FAIL", "reason": "not certified end to end for the requested portfolio"} for key in LEAN_GATES},
            "research_validity": "reconstructed_membership_exploratory", "survivorship_bias_risk": "source_dependent_incomplete"}


def coverage_v2(master, database: Path, output: Path, catalog: dict, *, secondary: Path | None = None) -> dict:
    """Year/exchange/session counts, deduplicated by security within each group.

    Sessions are the local SPY calendar, not an assertion of exhaustive market
    history. No-price and partial-price identities stay in every denominator.
    """
    output.mkdir(parents=True, exist_ok=True)
    f = master.frame.copy()
    f["valid_to"] = f.valid_to.fillna(master.coverage_end)
    f["interval_id"] = np.arange(len(f))
    with duckdb.connect(str(database), read_only=True) as c:
        c.execute("SET memory_limit='2GB'")
        sessions = pd.DatetimeIndex([r[0] for r in c.execute("SELECT date FROM daily_bars WHERE symbol='SPY' ORDER BY date").fetchall()])
        c.register("quality_mappings", f)
        prices = c.execute("""SELECT m.interval_id,COUNT(b.date) bar_rows,MIN(b.date) first_bar,MAX(b.date) last_bar,
            MEDIAN(b.close*b.volume) median_dollar_volume
            FROM quality_mappings m LEFT JOIN daily_bars b ON m.security_id=b.security_id
            AND m.symbol=b.symbol AND b.date BETWEEN m.valid_from AND m.valid_to GROUP BY m.interval_id""").df()
        current = {r[0] for r in c.execute("SELECT symbol FROM assets WHERE upper(trim(status))='ACTIVE'").fetchall()}
        parts = []
        for year in range(master.coverage_start.year, master.coverage_end.year + 1):
            year_sessions = sessions[sessions.year == year]
            if not len(year_sessions):
                continue
            first, last = year_sessions.min(), year_sessions.max()
            subset = f[f.valid_from.le(last) & f.valid_to.ge(first)].copy()
            subset["year"] = year
            subset["start"] = subset.valid_from.clip(lower=first)
            subset["end"] = subset.valid_to.clip(upper=last)
            expected = np.searchsorted(year_sessions, subset.end.to_numpy(), side='right') - np.searchsorted(year_sessions, subset.start.to_numpy())
            subset["expected"] = expected
            c.register("quality_year", subset)
            counts = c.execute("""SELECT m.interval_id,COUNT(b.date) observed FROM quality_year m
                LEFT JOIN daily_bars b ON m.security_id=b.security_id AND m.symbol=b.symbol
                AND b.date BETWEEN m.start AND m.end GROUP BY m.interval_id""").df()
            parts.append(subset.merge(counts, on='interval_id', validate='one_to_one'))
    intervals = f.merge(prices, on='interval_id', validate='one_to_one')
    intervals["expected"] = np.searchsorted(sessions, intervals.valid_to.to_numpy(), side='right') - np.searchsorted(sessions, intervals.valid_from.to_numpy())
    intervals["missing"] = (intervals.expected - intervals.bar_rows).clip(lower=0)
    secondary_symbols = set()
    secondary_ids = set()
    if secondary is not None:
        s = pd.read_csv(secondary, keep_default_na=False)
        claims = s.loc[s.source.eq('delisted')].copy()
        claims['event_date'] = pd.to_datetime(claims.source_delisting_date,format='%Y-%m-%d',errors='coerce')
        for claim in claims.dropna(subset=['event_date']).itertuples(index=False):
            scope = f.symbol.eq(claim.symbol) & f.valid_from.le(claim.event_date) & (f.valid_to+pd.Timedelta(days=7)).ge(claim.event_date)
            secondary_ids.update(f.loc[scope,'security_id'])
        secondary_symbols = set(f.loc[f.security_id.isin(secondary_ids),'symbol'])
    suspensions = {e['security_id']: e for e in catalog['events'] if e['event_type']=='trading_suspension' and e['confidence']=='verified'}
    delistings = {e['security_id']: e for e in catalog['events'] if e['event_type']=='delisting' and e['confidence']=='verified'}
    current_ids = set(master.eligible_on(master.coverage_end).security_id)
    years = pd.concat(parts, ignore_index=True)
    records = []
    for (year, exchange), group in years[years.eligible].groupby(['year','exchange'],sort=True):
        securities = group.groupby('security_id').agg(expected=('expected','sum'),observed=('observed','sum'),
                                                     verified=('resolution_status',lambda x:x.eq('verified').all()))
        ids = set(securities.index)
        retired = {i for i in ids & suspensions.keys() if pd.Timestamp(suspensions[i]['effective_date']).year >= year}
        records.append({'year':int(year),'exchange':exchange,'eligible_common_count':len(ids),
            'active_survivor_count':len(ids & current_ids),'active_survivor_definition':'same identity observed eligible at master coverage end',
            'later_delisted_count':len(ids & delistings.keys()),'later_exchange_retired_verified_count':len(retired),
            'secondary_delist_claim_symbols':len(set(group.loc[group.security_id.isin(secondary_ids),'symbol'])),
            'identity_verified_count':int(securities.verified.sum()),'identity_unresolved_count':int((~securities.verified).sum()),
            'price_complete_count':int((securities.expected.gt(0)&securities.observed.eq(securities.expected)).sum()),
            'partial_price_count':int((securities.observed.gt(0)&securities.observed.lt(securities.expected)).sum()),
            'no_price_count':int((securities.expected.gt(0)&securities.observed.eq(0)).sum()),
            'no_expected_sessions_count':int(securities.expected.eq(0).sum()),
            'terminal_price_available_count':sum(bool(intervals.loc[intervals.security_id.eq(i),'last_bar'].max()==pd.Timestamp(suspensions[i]['last_tradable_session'])) for i in retired),
            'confirmed_delisting_date_count':len(ids & delistings.keys()),
            'price_before_delisting_complete_count':None if not ids & delistings.keys() else 0,
            'expected_security_sessions':int(securities.expected.sum()),'observed_security_sessions':int(securities.observed.sum())})
    securities = intervals[intervals.eligible].groupby('security_id').agg(expected=('expected','sum'),observed=('bar_rows','sum'),missing=('missing','sum'))
    common = {'eligible_common_episodes':len(securities),'no_price':int(securities.observed.eq(0).sum()),
              'partial_price':int((securities.observed.gt(0)&securities.missing.gt(0)).sum()),
              'complete_available_interval':int((securities.expected.gt(0)&securities.missing.eq(0)).sum()),
              'insufficient_warmup_126':int(securities.observed.lt(126).sum()),
              'expected_security_sessions':int(securities.expected.sum()),'missing_security_sessions':int(securities.missing.sum())}
    queue = []
    for identity, group in intervals.groupby('security_id',sort=True):
        missing, expected = int(group.missing.sum()), int(group.expected.sum())
        if not missing and int(group.bar_rows.sum()) > 0:
            continue
        eligible = bool(group.eligible.any())
        symbols = sorted(set(group.symbol))
        liquidity = group.median_dollar_volume.max()
        secondary_claim = identity in secondary_ids
        tier = 3 if not eligible else 2 if pd.notna(liquidity) and liquidity < 1000000 else 1
        queue.append({'security_id':identity,'symbols':symbols,'tier':tier,'eligible_common':eligible,
            'missing_sessions':missing,'observed_sessions':int(group.bar_rows.sum()),'expected_sessions':expected,
            'secondary_delist_claim':secondary_claim,'not_observed_current_identity':identity not in current_ids,
            'median_dollar_volume':None if pd.isna(liquidity) else float(liquidity),
            'priority_evidence':'secondary claim + missing eligible prices' if secondary_claim and eligible else 'observed liquidity below frozen tradability minimum' if tier==2 else 'liquidity unknown; retain potential high impact' if tier==1 else 'ineligible type',
            'identity_status':'verified' if group.resolution_status.eq('verified').all() else 'unresolved'})
    queue.sort(key=lambda x:(x['tier'],not x['secondary_delist_claim'],not x['not_observed_current_identity'],-x['missing_sessions'],x['security_id']))
    candidates = episode_candidates(master.frame)
    classified = Counter(kind for r in candidates for kind in r['classes'])
    report = {'schema_version':2,'master_version':master.manifest['source_version'],'fingerprint':master.fingerprint,
              'reporter_code_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
              'evidence_catalog_sha256':digest(catalog),
              'secondary_evidence_sha256':hashlib.sha256(secondary.read_bytes()).hexdigest() if secondary else None,
              'priority_queue_sha256':digest(queue),'episode_candidates_sha256':digest(candidates),
              'calendar_start':str(sessions.min().date()),'calendar_end':str(sessions.max().date()),
              'common':common,'by_year_exchange':records,'priority_queue_counts':dict(Counter(r['tier'] for r in queue)),
              'multi_episode_tickers':len(candidates),'episode_candidate_classes':dict(classified),
              'verified_rename_events':sum(e['event_type']=='symbol_change' for e in catalog['events']),
              'classification':master.frame.groupby(['security_type','classification_confidence'],dropna=False).size().reset_index(name='intervals').to_dict('records'),
              'identity':dict(Counter(master.frame.resolution_status)),
              'limitations':['no-price denominator preserved','calendar ends before master observations',
                  'snapshot source excludes OTC; suspension does not prove economic disappearance',
                  'candidate classes can overlap and never merge identities','all other vendor bar identity remains uncertified']}
    snapshot_file = master.csv_path.with_name('snapshot-audit.json')
    if snapshot_file.exists():
        audit = json.loads(snapshot_file.read_text(encoding='utf-8'))
        accepted = [r for r in audit['snapshots'] if r.get('accepted')]
        source_years = []
        for year in sorted({r['date'][:4] for r in accepted}):
            subset = [r for r in accepted if r['date'].startswith(year)]
            source_years.append({'year':int(year),'accepted_snapshots':len(subset),
                'population_min':min(r['count'] for r in subset),'population_max':max(r['count'] for r in subset),
                'unknown_type_min':min(r.get('security_type_counts',{}).get('unknown',0) for r in subset),
                'unknown_type_max':max(r.get('security_type_counts',{}).get('unknown',0) for r in subset),
                'exchange_sets':sorted({','.join(sorted(r.get('exchange_counts',{}))) for r in subset})})
        times = pd.to_datetime([r['available_at'] for r in accepted],utc=True).tz_convert('America/New_York')
        report['primary_source_audit'] = {'accepted_snapshots':len(accepted),'year_profiles':source_years,
            'missing_calendar_snapshot_days':len(audit['missing_snapshot_dates']),
            'anomalies':audit['anomalies'],'commits_at_or_after_16_et':int((times.hour>=16).sum()),
            'population':'NASDAQ Screener exchange-filtered observations, not official full security directory',
            'otc_coverage':False,'native_security_ids':False,'native_instrument_flags':False,
            'snapshot_available_times':'UTC commits, close/next-calendar-day conservative availability',
            'disappear_reappear_candidates':len(candidates),'structural_limit':'small omissions and name/type changes may evade total-jump rejection'}
    report['scorecard'] = scorecard(master, common, catalog['events'])
    report['semantic_sha256'] = digest(report)
    intervals.to_csv(output/'coverage-v2-intervals.csv',index=False)
    (output/'coverage-v2.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (output/'price-priority-queue.json').write_text(json.dumps(queue,indent=2),encoding='utf-8')
    (output/'episode-candidates.json').write_text(json.dumps(candidates,indent=2),encoding='utf-8')
    return report


def difference_reasons(master, comparisons: list[dict], catalog: dict) -> list[dict]:
    """Explain only what evidence supports; absence alone never proves future IPO."""
    records = []
    for item in comparisons:
        if 'date' not in item:
            continue
        day = pd.Timestamp(item['date'])
        observed = master.observed_on(day).set_index('symbol')
        claims = []
        for direction,key in [('pit_only','pit_only_symbols'),('current_only','current_only_symbols')]:
            for symbol in item.get(key,[]):
                reason,confidence='source_scope_mismatch_or_unresolved','unresolved'
                if symbol in observed.index:
                    row=observed.loc[symbol]
                    if not row.eligible:
                        reason,confidence='product_type_filtering',row.get('classification_confidence','inferred')
                    else:
                        terminal=[e for e in catalog['events'] if e['security_id']==row.security_id and e['event_type'] in ('delisting','trading_suspension') and pd.Timestamp(e['effective_date'])>day]
                        if terminal:
                            reason,confidence=('later_delisted' if terminal[0]['event_type']=='delisting' else 'later_exchange_retired'),'verified'
                        elif row.resolution_status!='verified':
                            reason='unresolved_identity_or_current_source_scope'
                else:
                    mappings=[m for m in catalog['mappings'] if m['symbol']==symbol and m['confidence']=='verified']
                    listings=[e for e in catalog['events'] if e['event_type']=='listing' and any(m['security_id']==e['security_id'] for m in mappings)]
                    if any(pd.Timestamp(e['effective_date'])>day for e in listings):
                        reason,confidence='future_listing','verified'
                    elif any(pd.Timestamp(m['valid_from'])>day for m in mappings):
                        reason,confidence='ticker_rename_or_reuse_before_symbol_effective','verified'
                claims.append({'symbol':symbol,'direction':direction,'reason':reason,'confidence':confidence})
        records.append({'date':item['date'],'counts':dict(Counter(x['direction']+':'+x['reason'] for x in claims)),
                        'details':claims,'limitations':'membership-source differences; price/warmup/strategy differences are separate Scanner funnel evidence'})
    return records

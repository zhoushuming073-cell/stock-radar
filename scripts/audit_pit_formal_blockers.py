"""Recompute a frozen formal closure and produce one local row per security."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import duckdb
import pandas as pd

from radar.lab.universe import LocalSecurityMaster
from radar.pit.features import file_hash
from radar.pit.run import local_dependency, readiness, save_dependency, verify_dependencies


def audit(root, reference, metadata, output, *, frozen=False):
    old = json.loads(reference.read_text(encoding='utf-8'))
    master = LocalSecurityMaster(root/'data/security-master.csv', root/'data/security-master-manifest.json')
    if frozen:
        # The real queue preparation already reread bars/population. Replay its
        # exact byte-locked result; never silently recompute a different Run.
        verify_dependencies(old)
        if old['universe_fingerprint'] != master.fingerprint:
            raise ValueError('inventory frozen manifest is not the installed universe')
        manifest=old
    else:
        with duckdb.connect(master.feature_store['database'], read_only=True) as c:
            frame = c.execute('SELECT date,security_id FROM daily_features WHERE date BETWEEN ? AND ?', old['window'][:2]).df()
        manifest = local_dependency(root, master, metadata, frame, pd.to_datetime(old['calendar']), old['signals'])
    report = readiness(manifest)
    output.mkdir(parents=True, exist_ok=True)
    ref = save_dependency(root, manifest)
    reasons = defaultdict(dict)
    for gate, values in report['reasons_by_gate'].items():
        for value in values:
            identity = value.split(':', 1)[0]
            reasons[identity].setdefault(gate, []).append(value)
    gaps = pd.DataFrame([(r['security_id'], s, d) for r in manifest['dependencies']
                         for s in r['symbols'] for d in r['missing_sessions']],
                        columns=['security_id','symbol','date'])
    with duckdb.connect(str(root/'data/phase2-research.duckdb'), read_only=True) as c:
        c.register('gap_candidates', gaps)
        local = c.execute('''SELECT g.security_id,COUNT(DISTINCT g.date) n FROM gap_candidates g
            JOIN daily_bars b ON b.symbol=g.symbol AND b.date=CAST(g.date AS DATE) GROUP BY 1''').fetchall()
    local = dict(local)
    probe_path=root/'data/pit/clearance/unpriced-source-probes.json'
    probes={r['security_id']:r for r in json.loads(probe_path.read_text(encoding='utf-8'))['rows']} if probe_path.exists() else {}
    symbol_ids = master.frame.groupby('symbol').security_id.nunique().to_dict()
    rows=[]
    for r in manifest['dependencies']:
        sid=r['security_id']; mappings=r['mappings']; cert=r['certificate']
        verified = all(m.get('resolution_status')=='verified' for m in mappings)
        reuse = any(symbol_ids.get(s,0)>1 for s in r['symbols'])
        stratum = ('C' if verified and len(r['symbols'])>1 else 'D' if verified and len({m['exchange'] for m in mappings})>1
                   else 'B' if verified else 'E' if reuse else 'F' if any(m.get('security_name') for m in mappings) else 'H')
        fully_missing=len(r['missing_sessions'])==len(r['required_sessions'])
        probe=probes.get(sid,{})
        category=('identity-unresolved' if not verified else 'recoverable-via-known-source'
                  if local.get(sid) or probe.get('source_prices_found') else 'source-unavailable') if fully_missing else None
        rows.append({'security_id':sid,'symbols':r['symbols'],'symbol_intervals':mappings,
            'required_start':min(r['required_sessions']),'required_end':max(r['required_sessions']),
            'required_sessions':len(r['required_sessions']),'missing_sessions':r['missing_sessions'],
            'price_completeness':1-len(r['missing_sessions'])/len(r['required_sessions']),
            'identity_status':'verified' if verified else 'unresolved','identity_stratum':stratum,
            'security_types':sorted({m['security_type'] for m in mappings}),
            'membership_status':'source completeness unresolved', 'corporate_action_status':
                'reviewed' if cert.get('action_coverage_verified') else 'coverage unreviewed',
            'terminal_status':'known events handled' if not reasons[sid].get('Terminal') else 'blocked',
            'ticker_reuse_risk':reuse,'rename_risk':len(r['symbols'])>1,
            'license_status':cert.get('license','scope unreviewed'),
            'adjustment_basis_status':cert.get('price_basis','scope unreviewed'),
            'price_sources':r['price_sources'], 'source_price_availability':{
                'local_broker_missing_date_candidates':local.get(sid,0),
                'dolt_missing_date_probe_hits':probe.get('source_prices_found'),
                'dolt_probe_dates':probe.get('missing_dates_probed'),
                'dolt_probe_receipt_file':str(probe_path) if probe else None,
                'decision':'ticker/date availability only; identity and basis review required'},
            'no_price_category':category, 'priority':'P0',
            'recovery_priority':'P1' if verified or local.get(sid) else 'P2',
            'final_gate_reasons':reasons[sid]})
    counts={'securities':len(rows),'signals':len(manifest['signals']),
        'required_prices':sum(len(r['required_sessions']) for r in manifest['dependencies']+manifest['benchmarks']),
        'missing_prices':sum(len(r['missing_sessions']) for r in manifest['dependencies']+manifest['benchmarks']),
        'fully_unpriced':sum(r['no_price_category'] is not None for r in rows),
        'partially_unpriced':sum(0<len(r['missing_sessions'])<r['required_sessions'] for r in rows),
        'identity_blocked':sum(r['identity_status']!='verified' for r in rows),
        'action_coverage_reviewed':sum(r['corporate_action_status']=='reviewed' for r in rows),
        'local_gap_candidates':sum(local.values()),'identity_strata':dict(Counter(r['identity_stratum'] for r in rows)),
        'no_price_categories':dict(Counter(r['no_price_category'] for r in rows if r['no_price_category'])),
        'gate_reason_counts':{k:len(v) for k,v in report['reasons_by_gate'].items()}}
    (output/'blocker-inventory.json').write_text(json.dumps({'dependency':ref,'counts':counts,'rows':rows},indent=2),encoding='utf-8')
    (output/'readiness.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps({'dependency':ref,'counts':counts},indent=2),encoding='utf-8')
    print(json.dumps(counts),flush=True)
    return manifest


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--dependency',type=Path,required=True)
    p.add_argument('--metadata',type=Path,required=True,help='prior gated-attempt receipt with metadata')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--frozen',action='store_true',help='replay the freshly recomputed formal queued manifest and verify every physical lock')
    a=p.parse_args()
    audit(Path.cwd(),a.dependency,json.loads(a.metadata.read_text(encoding='utf-8'))['metadata'],a.output,frozen=a.frozen)

"""Annotate the missing-price queue with frozen Scanner selection witnesses.

The 12 audited sessions are a bounded sample, not all-history candidate frequency.
No forward performance is read. Unpriced identities remain potential Tier 1 gaps.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

from radar.lab.universe import LocalSecurityMaster
from radar.pit.builder import digest
from radar.pit.features import file_hash


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build', type=Path, required=True)
    args = parser.parse_args()
    master = LocalSecurityMaster(args.build/'security-master.csv', args.build/'security-master-manifest.json')
    output = Path('data/pit/reports')/master.manifest['source_version']
    audit = json.loads((output/'coverage-v2.json').read_text(encoding='utf-8'))
    queue = json.loads((output/'price-priority-queue.json').read_text(encoding='utf-8'))
    comparison_file = output/'scanner-selection-comparison.json'
    scanner = json.loads(comparison_file.read_text(encoding='utf-8'))
    if (audit['fingerprint'] != master.fingerprint or audit['priority_queue_sha256'] != digest(queue)
            or scanner['universe_fingerprint'] != master.fingerprint
            or scanner['feature_store']['database_sha256'] != master.feature_store['database_sha256']):
        raise ValueError('Scanner/coverage provenance differs from installed build')
    counts = Counter(identity for item in scanner['dates'] for identity in item['pit_candidate_security_ids'].values())
    for row in queue:
        row['selected_scanner_witnesses'] = counts[row['security_id']]
    queue.sort(key=lambda row:(row['tier'], -row['selected_scanner_witnesses'],
        not row['secondary_delist_claim'], not row['not_observed_current_identity'],
        -row['missing_sessions'], row['security_id']))
    report = {'master_version':master.manifest['source_version'], 'fingerprint':master.fingerprint,
              'coverage_sha256':audit['semantic_sha256'], 'scanner_file_sha256':file_hash(comparison_file),
              'annotator_code_sha256':file_hash(Path(__file__)), 'witness_dates':[r['date'] for r in scanner['dates']],
              'scope':'selected candidates on audited dates only; liquidity-unknown Tier 1 is potential impact',
              'future_performance_examined':False, 'queue':queue}
    (output/'price-priority-scanner-witnesses.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps({'queue_rows':len(queue),'selected_identities_with_price_gaps':sum(r['selected_scanner_witnesses']>0 for r in queue)}))

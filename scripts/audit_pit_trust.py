"""Offline v2 coverage, conflicts, identity/type/event evidence and scorecard."""
import argparse
import json
from pathlib import Path

from radar.lab.universe import LocalSecurityMaster
from radar.pit.features import file_hash
from radar.pit.quality import coverage_v2, difference_reasons
from radar.pit.trust import load_catalog

if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--catalog',type=Path,default=Path('config/pit_trust_evidence.json'))
    p.add_argument('--secondary',type=Path)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    m=LocalSecurityMaster(a.build/'security-master.csv',a.build/'security-master-manifest.json')
    if not m.feature_store:
        p.error('bind PIT features before auditing')
    db=Path(m.feature_store['database'])
    if file_hash(db)!=m.feature_store['database_sha256']:
        p.error('PIT feature database bytes changed')
    output=a.output or Path('data/pit/reports')/m.manifest['source_version']
    r=coverage_v2(m,db,output,load_catalog(a.catalog),secondary=a.secondary)
    for source,name in [('trust-evidence.json','identity-classification-events-conflicts.json')]:
        (output/name).write_bytes((a.build/source).read_bytes())
    comparison=output/'current-vs-pit.json'
    if comparison.exists():
        explained=difference_reasons(m,json.loads(comparison.read_text(encoding='utf-8')),load_catalog(a.catalog))
        (output/'current-vs-pit-reasons.json').write_text(json.dumps(explained,indent=2),encoding='utf-8')
    print(json.dumps({k:r[k] for k in ['common','multi_episode_tickers','episode_candidate_classes','identity','semantic_sha256']},indent=2))

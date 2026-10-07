"""Write a new local unified action evidence store; completeness is never inferred."""
import argparse
import json
from pathlib import Path
from radar.pit.actions import write_action_store
from radar.pit.trust import load_catalog

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--catalog',type=Path,default=Path('config/pit_trust_evidence.json'))
    p.add_argument('--raw',type=Path,default=Path('data/pit/raw/official-evidence'))
    p.add_argument('--reviews',type=Path)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    print(json.dumps(write_action_store(load_catalog(a.catalog,a.raw),
        json.loads(a.reviews.read_text(encoding='utf-8')) if a.reviews else {},a.output),indent=2))

"""Build a private, immutable Box Labeling v1 task bundle from frozen RI v1."""
import argparse
import json
from pathlib import Path
from radar.box_labeling.dataset import build


if __name__ == '__main__':
    p=argparse.ArgumentParser()
    p.add_argument('--research-root',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--config',type=Path,default=Path('config/box_labeling_v1.yaml'))
    p.add_argument('--pool-limit',type=int,default=1800)
    a=p.parse_args()
    print(json.dumps(build(a.output,a.research_root,a.config,pool_limit=a.pool_limit),indent=2))

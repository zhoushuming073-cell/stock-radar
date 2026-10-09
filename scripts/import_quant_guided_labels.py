from pathlib import Path
import argparse
import json
from radar.vision.quant_labels import import_labels

if __name__=='__main__':
    p=argparse.ArgumentParser(); p.add_argument('export',type=Path)
    p.add_argument('--bundle',type=Path,default=Path('data/vision-research/quant-guided-v1/ready'))
    p.add_argument('--origin',choices=['human','smoke'],required=True); a=p.parse_args()
    print(json.dumps(import_labels(a.bundle,a.export,a.origin),ensure_ascii=False,indent=2))

from pathlib import Path
import argparse,json
from radar.vision.dual_store import import_export
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('export',type=Path);p.add_argument('--origin',required=True,choices=['human','smoke']);a=p.parse_args()
    print(json.dumps(import_export(Path('.local/vision-dual-stage-v3'),a.export,a.origin),indent=2))

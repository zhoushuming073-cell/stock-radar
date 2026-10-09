from pathlib import Path
import argparse,json
from radar.vision.dual_dataset import build,verify
if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--verify-only',action='store_true');a=p.parse_args()
    if not a.verify_only:build(Path.cwd())
    print(json.dumps(verify(Path.cwd()),indent=2))

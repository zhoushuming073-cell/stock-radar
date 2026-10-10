"""Generate own-source-only Q2 v1.2 Cloud files; does not launch a remote job."""
from pathlib import Path
import argparse
import json
from radar.research.high_beta.cloud.build import prepare


def main():
    root=Path(__file__).resolve().parents[1]
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out',type=Path,default=root/'data/research/q2-v12-cloud-exploratory')
    args=parser.parse_args()
    result=prepare(root,args.out)
    print(json.dumps({'status':result['status'],'upload':str(args.out/'upload'),
        'files':result['upload_files'],'receipt':result['receipt']['selector_sha256']}))


if __name__=='__main__':main()

import argparse
import json
from pathlib import Path
from radar.vision.verification import verify

def main():
    parser=argparse.ArgumentParser(description="Fail-closed blind pilot verification")
    parser.add_argument("--bundle",type=Path,default=Path("data/vision-research/pilot-v1"))
    args=parser.parse_args()
    print(json.dumps(verify(args.bundle),ensure_ascii=False,indent=2))
    return 0

if __name__=="__main__":raise SystemExit(main())

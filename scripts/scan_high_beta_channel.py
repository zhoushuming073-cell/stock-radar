"""Independent Q2 v1.2 latest-session scan; no historical outcomes/orders."""
import argparse
import json
from pathlib import Path
from radar.research.high_beta.daily import snapshot,save
from radar.research.candidates import fingerprint


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--asof');p.add_argument('--workers',type=int,choices=[1,2,4],default=1)
    p.add_argument('--verify-parallel',action='store_true')
    args=p.parse_args();root=Path(__file__).resolve().parents[1]
    r=snapshot(root,args.asof,args.workers,progress=lambda x:print(x,flush=True))
    if args.verify_parallel:
        other=snapshot(root,args.asof,4 if args.workers==1 else 1,progress=lambda x:print('Repeat '+x,flush=True))
        if other!=r:raise ValueError('Real serial/parallel full snapshot mismatch')
        proof={'same_input_serial_parallel':True,'snapshot_hash':fingerprint(r),'as_of':r['as_of']}
        out=root/'data/research/high-beta-channel-v1.2';out.mkdir(parents=True,exist_ok=True)
        (out/'parallel-acceptance.json').write_text(json.dumps(proof,indent=2))
    path=save(root,r)
    print(json.dumps({'path':str(path),'snapshot_hash':fingerprint(r),'version':r['version'],'as_of':r['as_of'],
                     'funnel':r['funnel'],'reasons':r['reason_counts']},indent=2))


if __name__=='__main__':main()

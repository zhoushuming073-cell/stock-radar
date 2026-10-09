"""One-command latest completed US-session Q1/Q2 watchlist. Local, no network/orders."""
import argparse
import json
from pathlib import Path
from radar.research.daily import snapshot,save_snapshot,csv_rows

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--asof');p.add_argument('--method',choices=['q1','q2','all'],default='all')
    p.add_argument('--top',type=int,default=20);p.add_argument('--out',type=Path)
    args=p.parse_args();root=Path(__file__).resolve().parents[1]
    if args.out is not None and not args.out.resolve().is_relative_to((root/'data').resolve()):
        p.error('Detailed output must remain in ignored data/ storage')
    r=snapshot(root,args.asof,args.method,args.top,progress=lambda msg:print(msg,flush=True))
    path=save_snapshot(root,r)
    if args.out:
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(csv_rows(r) if args.out.suffix=='.csv' else json.dumps(r,indent=2,allow_nan=False),encoding='utf-8')
    print(json.dumps({'path':str(path),'as_of':r['as_of'],'freshness':r['freshness'],
                      'q1':r['q1_counts'],'q2':r['q2_counts'],'overlap':r['overlap_count'],
                      'eligible':r['universe_count'],'scored':r['scored_counts']},indent=2))

if __name__=='__main__':main()


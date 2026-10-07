"""Seed/replay the P0 run closure queue without overwriting installed artifacts."""
import argparse
import json
from pathlib import Path

from radar.pit.run import verify_dependencies
from radar.pit.resolution import ResolutionQueue, work


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dependency',type=Path,required=True)
    parser.add_argument('--root',type=Path,default=Path.cwd())
    parser.add_argument('--queue',type=Path,default=Path('data/pit/resolution.sqlite3'))
    parser.add_argument('--limit',type=int,default=20)
    parser.add_argument('--network',action='store_true')
    parser.add_argument('--price-pin')
    parser.add_argument('--retry-failed',action='store_true',help='retry at most three worker attempts; past outcomes retained')
    args=parser.parse_args()
    manifest=json.loads(args.dependency.read_text(encoding='utf-8'));verify_dependencies(manifest)
    queue=ResolutionQueue(args.queue);queue.seed(manifest)
    if args.retry_failed:queue.retry_failed()
    outcomes=work(args.root,queue,limit=args.limit,network=args.network,pin=args.price_pin)
    target=args.queue.with_suffix('.worker-report.json')
    target.write_text(json.dumps({'dependency_sha256':manifest['dependency_sha256'],
                                 'outcomes':outcomes,'queue':queue.summary()},indent=2),encoding='utf-8')
    print(json.dumps({'queue':queue.summary(),'report':str(target)},indent=2))


if __name__=='__main__':main()

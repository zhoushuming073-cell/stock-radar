"""Offline import; real SPY sessions come from the preserved research snapshot."""
import argparse
import json
from pathlib import Path

import duckdb

from radar.lab.universe import LocalSecurityMaster
from radar.pit.price_import import accept_prices

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--build',type=Path,required=True)
    p.add_argument('--raw',type=Path,default=Path('data/pit/raw/public-prices'))
    p.add_argument('--review',type=Path,default=Path('config/pit_public_price_review.json'))
    p.add_argument('--calendar',type=Path,default=Path('data/phase2-research.duckdb'))
    p.add_argument('--raw-actions',type=Path)
    a=p.parse_args()
    m=LocalSecurityMaster(a.build/'security-master.csv',a.build/'security-master-manifest.json')
    r=json.loads(a.review.read_text(encoding='utf-8'))
    with duckdb.connect(str(a.calendar),read_only=True) as c:
        r['sessions']=[str(x[0]) for x in c.execute("SELECT date FROM daily_bars WHERE symbol='SPY' ORDER BY date").fetchall()]
    print(json.dumps(accept_prices(a.raw,r,m,a.build/'external-prices.duckdb',
        raw_actions=json.loads(a.raw_actions.read_text(encoding='utf-8')) if a.raw_actions else None),indent=2))

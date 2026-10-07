"""Explicit, bounded, free price acquisition into ignored raw quarantine."""
import argparse
from pathlib import Path
import json
from radar.pit.public_prices import acquire_symbol

if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--symbol", required=True)
    p.add_argument("--pin", required=True)
    p.add_argument("--start", required=True)
    p.add_argument("--end", required=True)
    p.add_argument("--cache", type=Path, default=Path("data/pit/raw/public-prices"))
    a = p.parse_args()
    print(json.dumps(acquire_symbol(a.symbol, a.pin, a.start, a.end, a.cache)), flush=True)

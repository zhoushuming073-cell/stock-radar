"""Build Phase 2A-F feature and label tables from a local research DB."""

import argparse
import json
from pathlib import Path
import sys

from radar.research.pipeline import build_research_tables


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=ROOT / "data" / "phase2-research.duckdb")
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "research.yaml")
    parser.add_argument("--max-symbols", type=int)
    parser.add_argument("--progress", action="store_true")
    args = parser.parse_args()
    if args.max_symbols is not None and args.max_symbols < 1:
        parser.error("max-symbols must be positive")
    progress = (lambda item: print(json.dumps(item), file=sys.stderr, flush=True)) if args.progress else None
    print(json.dumps(build_research_tables(args.database, args.config,
                                           max_symbols=args.max_symbols, progress=progress),
                     ensure_ascii=False))


if __name__ == "__main__":
    main()

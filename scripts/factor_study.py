"""Run Phase 2F factor buckets on purged Train and Validation only."""

import argparse
import json
from pathlib import Path

from radar.research.event_study import run_factor_event_study


ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, default=ROOT / "data" / "phase2-research.duckdb")
    parser.add_argument("--config", type=Path, default=ROOT / "config" / "research.yaml")
    parser.add_argument("--output", type=Path, default=ROOT / "reports" / "phase2")
    args = parser.parse_args()
    print(json.dumps(run_factor_event_study(args.database, args.config, args.output), ensure_ascii=False))


if __name__ == "__main__":
    main()

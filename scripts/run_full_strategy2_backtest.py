"""Run the user's full-lifecycle Strategy 2 candidate on local historical data."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from radar.backtest.full_strategy2_runner import run_full_strategy2


ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--splits", nargs="+", choices=("train", "validation", "test"),
                        required=True)
    args = parser.parse_args()
    result = run_full_strategy2(
        ROOT / "data" / "phase2-research.duckdb",
        ROOT / "config" / "research.yaml",
        ROOT / "config" / "backtest.yaml",
        ROOT / "config" / "full_strategy2.yaml",
        ROOT / "data" / "research" / "full-strategy2-v1",
        splits=tuple(args.splits),
    )
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))

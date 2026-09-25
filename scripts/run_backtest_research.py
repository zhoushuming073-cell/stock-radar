"""Compare predeclared Strategy 2 candidates on Train and Validation only."""

import json
from pathlib import Path

from radar.backtest.runner import run_research_grid


ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    output = run_research_grid(
        ROOT / "data" / "phase2-research.duckdb",
        ROOT / "config" / "research.yaml",
        ROOT / "config" / "backtest.yaml",
        ROOT / "data" / "research" / "backtest-v1",
    )
    print(json.dumps(output, ensure_ascii=False))

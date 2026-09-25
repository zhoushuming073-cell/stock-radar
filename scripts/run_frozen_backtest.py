"""One-time final Test evaluation after strategy parameters are frozen."""

import json
from pathlib import Path

from radar.backtest.runner import run_frozen_test


ROOT = Path(__file__).resolve().parents[1]


if __name__ == "__main__":
    summary = run_frozen_test(ROOT / "config" / "frozen_backtest_v1.yaml")
    print(json.dumps(summary, ensure_ascii=False, allow_nan=False))

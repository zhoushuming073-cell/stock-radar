"""Read-only acceptance gate before promoting the full-cohort v3 research DB."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

from radar.research.asof import strict_asof_day
from radar.research.pipeline import BUILD_FEATURE_VERSION
from radar.schema import RESEARCH_COLUMNS


ROOT = Path(__file__).resolve().parents[1]
COMPARE = [name for name in RESEARCH_COLUMNS["daily_features"]
           if name not in {"symbol", "date", "feature_version", "computed_at",
                           "tradability_pass"}]


def verify(database: Path, config: Path, days: list[pd.Timestamp]) -> dict:
    with duckdb.connect(str(database), read_only=True) as connection:
        cohort = [row[0] for row in connection.execute("""
            SELECT a.symbol FROM assets a
            WHERE a.symbol NOT IN ('SPY','QQQ')
              AND upper(trim(a.asset_class))='US_EQUITY'
              AND upper(trim(a.status))='ACTIVE'
              AND EXISTS (SELECT 1 FROM daily_bars b WHERE b.symbol=a.symbol)
            ORDER BY a.symbol
        """).fetchall()]
        latest = connection.execute("""
            SELECT status FROM research_runs WHERE feature_version=?
            ORDER BY created_at DESC LIMIT 1
        """, [BUILD_FEATURE_VERSION]).fetchone()
        expected_status = f"built_asof_{len(cohort)}_of_{len(cohort)}_symbols"
        if latest is None or latest[0] != expected_status:
            raise ValueError("no completed full-cohort As-Of build")
        built = {row[0] for row in connection.execute("""
            SELECT DISTINCT symbol FROM daily_features WHERE feature_version=?
        """, [BUILD_FEATURE_VERSION]).fetchall()}
        if built != set(cohort):
            raise ValueError(f"v3 cohort mismatch: missing={len(set(cohort)-built)}, "
                             f"extra={len(built-set(cohort))}")
        checked = []
        for day in days:
            day = pd.Timestamp(day).normalize()
            strict = strict_asof_day(connection, day, config, cohort).sort_values("symbol")
            fields = ",".join(f'"{name}"' for name in COMPARE)
            fast = connection.execute(f"""
                SELECT symbol,tradability_pass,{fields}
                FROM daily_features WHERE feature_version=? AND date=? ORDER BY symbol
            """, [BUILD_FEATURE_VERSION, day.date()]).df()
            if strict.symbol.tolist() != fast.symbol.tolist():
                raise ValueError(f"As-Of membership mismatch on {day.date()}")
            if strict.tradability_pass.tolist() != fast.tradability_pass.tolist():
                raise ValueError(f"As-Of eligibility mismatch on {day.date()}")
            for field in COMPARE:
                if field not in strict:
                    raise ValueError(f"strict replay omitted {field}")
                left = pd.to_numeric(strict[field], errors="coerce").astype(float)
                right = pd.to_numeric(fast[field], errors="coerce").astype(float)
                if not np.allclose(left, right,
                                   equal_nan=True, rtol=1e-9, atol=1e-9):
                    raise ValueError(f"As-Of {field} mismatch on {day.date()}")
            expected_breadth = fast.loc[
                fast.tradability_pass & fast.dist_ma_20.notna(), "dist_ma_20"].gt(0).mean()
            if not np.isclose(strict.market_breadth.iloc[0], expected_breadth,
                              equal_nan=True):
                raise ValueError(f"As-Of breadth mismatch on {day.date()}")
            fast_rank = fast.loc[fast.elasticity_score.notna()].sort_values(
                ["elasticity_score", "symbol"], ascending=[False, True]).symbol.tolist()
            strict_rank = strict.loc[strict.elasticity_score.notna()].sort_values(
                ["elasticity_score", "symbol"], ascending=[False, True]).symbol.tolist()
            if fast_rank != strict_rank:
                raise ValueError(f"As-Of rank mismatch on {day.date()}")
            checked.append({"date": str(day.date()), "observed": len(fast),
                            "eligible": int(fast.tradability_pass.sum()),
                            "ranked": len(fast_rank), "breadth": float(expected_breadth)})
        return {"database": str(database), "version": BUILD_FEATURE_VERSION,
                "cohort": len(cohort), "checked_days": checked, "passed": True}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--config", type=Path, default=ROOT / "config/research.yaml")
    parser.add_argument("--day", type=pd.Timestamp, action="append", required=True)
    args = parser.parse_args()
    print(json.dumps(verify(args.database, args.config, args.day), ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Audit the exploratory full Strategy 2 Test ledger and lifecycle gates."""

import json
from pathlib import Path

import duckdb
import pandas as pd

from verify_final_backtest import verify


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "research" / "full-strategy2-v1"


def main() -> None:
    scenarios = pd.read_csv(OUTPUT / "scenario_summary.csv")
    base = scenarios.loc[(scenarios["split"] == "test") &
                         (scenarios["slippage_bps_per_side"] == 10)]
    if len(base) != 1:
        raise ValueError("expected one 10 bps exploratory Test summary")
    replay = verify(OUTPUT, "test_trades.csv", "test_equity.csv",
                    "test_orders.csv", float(base.iloc[0]["total_return"]))

    trades = pd.read_csv(OUTPUT / "test_trades.csv", parse_dates=["signal_date"])
    wanted = trades[["signal_date", "symbol"]].drop_duplicates().rename(
        columns={"signal_date": "date"})
    connection = duckdb.connect(str(ROOT / "data" / "phase2-research.duckdb"), read_only=True)
    connection.register("wanted_signals", wanted)
    try:
        features = connection.execute("""
            SELECT f.date, f.symbol, f.tradability_pass, f.elasticity_score,
                   f.ret_60, f.drawdown_60, f.drawdown_20, f.pullback_days_20,
                   f.decline_speed_prev_3, f.decline_acceleration,
                   f.failed_breakdown, f.support_reclaim, f.lower_wick_ratio,
                   f.close_location, f.volume_contraction, f.new_low_frequency_5,
                   f.ret_1, f.body_pct, f.rebound_from_low_5, f.dist_ma_5,
                   a.name AS security_name
            FROM wanted_signals w
            JOIN daily_features f ON f.date=w.date AND f.symbol=w.symbol
            JOIN assets a ON a.symbol=f.symbol
            WHERE f.feature_version='phase2a_f_v2'
        """).df()
    finally:
        connection.close()
    assert len(features) == len(wanted)
    prior_gain = (1 + features.ret_60) / (1 + features.drawdown_60) - 1
    absorption = (features.failed_breakdown.fillna(False) |
                  features.support_reclaim.fillna(False) |
                  ((features.lower_wick_ratio >= .25) &
                   (features.close_location >= .5)) |
                  (features.volume_contraction < .8))
    checks = {
        "liquid": features.tradability_pass.eq(True),
        "elasticity": features.elasticity_score >= 76.21433772581146,
        "prior_strength": prior_gain >= .13230715023626216,
        "pullback": features.drawdown_20.between(-.40, -.08) &
                    features.pullback_days_20.ge(2),
        "exhaustion": features.decline_speed_prev_3.lt(0) &
                      features.decline_acceleration.gt(0),
        "absorption": absorption,
        "no_effective_new_low": features.new_low_frequency_5.le(.2),
        "early_reversal": features.ret_1.gt(0) & features.body_pct.gt(0) &
                          features.close_location.ge(.5),
        "not_extended": features.rebound_from_low_5.le(.15) &
                        features.ret_1.le(.10) & features.dist_ma_5.le(.15),
        "exclude_named_funds": ~features.security_name.astype("string").str.contains(
            r"\bETF\b|\bETN\b|exchange.traded", case=False, regex=True, na=False),
    }
    for name, passed in checks.items():
        assert passed.fillna(False).all(), f"recorded trade failed {name}"
    result = {**replay, "full_strategy2_signal_rows_checked": len(features),
              "lifecycle_checks": sorted(checks)}
    (OUTPUT / "verification.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Post-test diagnostics only: groups never feed candidate selection."""

from pathlib import Path

import duckdb
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "research" / "final-test-v1"
DB = ROOT / "data" / "phase2-research.duckdb"


def main() -> None:
    trades = pd.read_csv(OUT / "backtest_trades.csv",
                         parse_dates=["signal_date", "entry_date", "exit_date"])
    equity = pd.read_csv(OUT / "backtest_daily_equity.csv", parse_dates=["date"])
    conn = duckdb.connect(str(DB), read_only=True)
    try:
        symbols = trades.symbol.drop_duplicates().tolist()
        places = ",".join("?" for _ in symbols)
        extra = conn.execute(f"""
            SELECT symbol, date, atr_pct_20 FROM daily_features
            WHERE feature_version='phase2a_f_v2' AND symbol IN ({places})
              AND date BETWEEN ? AND ?
        """, [*symbols, equity.date.min().date(), equity.date.max().date()]).df()
        spy = conn.execute("""
            SELECT date, close FROM daily_bars WHERE symbol='SPY'
              AND date<=? ORDER BY date
        """, [equity.date.max().date()]).df()
    finally:
        conn.close()
    extra["date"] = pd.to_datetime(extra["date"])
    trades = trades.merge(extra, left_on=["symbol", "signal_date"],
                          right_on=["symbol", "date"], how="left", validate="many_to_one")
    spy["date"] = pd.to_datetime(spy["date"])
    market = spy.set_index("date")["close"].astype(float)
    market_ok = market.ge(market.rolling(200, min_periods=200).mean())
    trades["market_regime"] = trades.signal_date.map(market_ok).map(
        {True: "SPY >= MA200", False: "SPY < MA200"}).fillna("unknown")
    trades["exit_year"] = trades.exit_date.dt.year.astype(str)
    trades["exit_quarter"] = trades.exit_date.dt.to_period("Q").astype(str)
    trades["elasticity_band"] = pd.cut(trades.elasticity_score,
                                        [0, 80, 85, 90, 95, 100], include_lowest=True).astype(str)
    trades["drawdown_band"] = pd.cut(trades.drawdown_20,
                                      [-float("inf"), -.4, -.3, -.2, -.1, 0]).astype(str)
    trades["atr_band"] = pd.cut(trades.atr_pct_20,
                                 [0, .02, .04, .06, .10, float("inf")], include_lowest=True).astype(str)
    trades["entry_gap_band"] = pd.cut(trades.entry_gap,
                                       [-.1, -.05, 0, .03, .05], include_lowest=True).astype(str)
    trades["holding_band"] = pd.cut(trades.holding_sessions,
                                     [0, 1, 2, 5, 10]).astype(str)
    dimensions = ["exit_year", "exit_quarter", "market_regime", "elasticity_band",
                  "drawdown_band", "atr_band", "entry_gap_band", "holding_band",
                  "exit_reason"]
    rows = []
    for dimension in dimensions:
        for bucket, part in trades.groupby(dimension, dropna=False, observed=True):
            rows.append({"dimension": dimension, "bucket": str(bucket),
                         "trades": len(part), "total_net_pnl": part.net_pnl.sum(),
                         "mean_net_return": part.net_return.mean(),
                         "median_net_return": part.net_return.median(),
                         "win_rate": part.net_pnl.gt(0).mean()})
    pd.DataFrame(rows).to_csv(OUT / "trade_diagnostics.csv", index=False)
    month_end = equity.set_index("date")["equity"].resample("ME").last()
    monthly = month_end.pct_change()
    if len(monthly):
        monthly.iloc[0] = month_end.iloc[0] / 1_000_000 - 1
    pd.DataFrame({"month": monthly.index.strftime("%Y-%m"),
                  "return": monthly.values, "ending_equity": month_end.values}).to_csv(
                      OUT / "monthly_returns.csv", index=False)
    print(f"diagnostics: {len(rows)} groups, {len(monthly)} months")


if __name__ == "__main__":
    main()

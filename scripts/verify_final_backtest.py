"""Independently replay final-Test entry/exit triggers and ledger invariants."""

import json
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "data" / "research" / "final-test-v1"
DB = ROOT / "data" / "phase2-research.duckdb"


def main() -> None:
    trades = pd.read_csv(OUTPUT / "backtest_trades.csv", parse_dates=["signal_date", "entry_date", "exit_date"])
    equity = pd.read_csv(OUTPUT / "backtest_daily_equity.csv", parse_dates=["date"])
    orders = pd.read_csv(OUTPUT / "backtest_orders.csv", parse_dates=["date"])
    summary = json.loads((OUTPUT / "backtest_summary.json").read_text(encoding="utf-8"))
    conn = duckdb.connect(str(DB), read_only=True)
    try:
        sessions = [pd.Timestamp(row[0]) for row in conn.execute("""
            SELECT date FROM daily_bars WHERE symbol='SPY'
              AND date BETWEEN ? AND ? ORDER BY date
        """, [equity.date.min().date(), equity.date.max().date()]).fetchall()]
        names = trades.symbol.drop_duplicates().tolist()
        placeholders = ",".join("?" for _ in names)
        bars = conn.execute(f"""
            SELECT symbol,date,open,close FROM daily_bars
            WHERE symbol IN ({placeholders}) AND date BETWEEN ? AND ?
        """, [*names, equity.date.min().date(), equity.date.max().date()]).df()
    finally:
        conn.close()
    bars["date"] = pd.to_datetime(bars["date"])
    price = bars.set_index(["date", "symbol"])
    position = {date: index for index, date in enumerate(sessions)}
    assert equity.date.tolist() == sessions, "equity calendar differs from SPY"
    assert not trades.empty, "no completed trades to audit"
    assert orders.loc[orders.status == "entered"].groupby("date").size().max() <= 3
    assert equity.cash.min() >= -1e-7
    assert np.allclose(equity.equity, equity.cash + equity.gross_exposure, atol=1e-6)
    assert abs(equity.equity.iloc[-1] - 1_000_000 - trades.net_pnl.sum()) < 1e-6
    component_error = (trades.gross_pnl - trades.buy_fee_total - trades.sell_fee_total
                       - trades.slippage_cost - trades.net_pnl).abs().max()
    assert component_error < 1e-6
    assert abs(summary["test"]["total_return"] - (equity.equity.iloc[-1] / 1_000_000 - 1)) < 1e-6
    assert not trades.duplicated(["symbol", "entry_date"]).any()

    checked = 0
    for trade in trades.itertuples(index=False):
        signal_i = position[trade.signal_date]
        entry_i = position[trade.entry_date]
        exit_i = position[trade.exit_date]
        assert entry_i == signal_i + 1, f"{trade.symbol}: entry is not next SPY session"
        assert trade.holding_sessions == exit_i - entry_i + 1 <= 10
        signal_close = price.loc[(trade.signal_date, trade.symbol), "close"]
        assert -.10 - 1e-12 <= trade.entry_reference / signal_close - 1 <= .05 + 1e-12
        assert abs(price.loc[(trade.entry_date, trade.symbol), "open"] - trade.entry_reference) < 1e-8
        basis = trade.entry_total / trade.quantity
        first_trigger = None
        for day_i in range(entry_i, exit_i + 1):
            key = (sessions[day_i], trade.symbol)
            if key not in price.index:
                continue
            row = price.loc[key]
            holding = day_i - entry_i + 1
            if holding > 1:
                move = row.open / basis - 1
                if move >= .05:
                    first_trigger = (day_i, "take_profit_gap", row.open)
                elif move <= -.10:
                    first_trigger = (day_i, "stop_loss_gap", row.open)
            if first_trigger is None:
                move = row.close / basis - 1
                if move >= .05:
                    first_trigger = (day_i, "take_profit_close", row.close)
                elif move <= -.10:
                    first_trigger = (day_i, "stop_loss_close", row.close)
                elif holding >= 10:
                    first_trigger = (day_i, "max_holding_period", row.close)
            if first_trigger is not None:
                break
        assert first_trigger is not None, f"{trade.symbol}: no legal exit trigger"
        expected_i, expected_reason, expected_price = first_trigger
        assert expected_i == exit_i and expected_reason == trade.exit_reason
        assert abs(expected_price - trade.exit_reference) < 1e-8
        checked += 1
    for symbol, group in trades.sort_values("entry_date").groupby("symbol"):
        previous_exit = None
        for trade in group.itertuples(index=False):
            assert previous_exit is None or trade.entry_date > previous_exit, f"{symbol}: overlapping lots"
            previous_exit = trade.exit_date
    result = {"status": "passed", "trades_replayed": checked,
              "sessions_checked": len(sessions), "max_daily_entries": int(
                  orders.loc[orders.status == "entered"].groupby("date").size().max()),
              "minimum_cash": float(equity.cash.min()),
              "ending_equity_reconciliation_error": float(
                  abs(equity.equity.iloc[-1] - 1_000_000 - trades.net_pnl.sum())),
              "maximum_trade_component_error": float(component_error)}
    (OUTPUT / "verification.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result))


if __name__ == "__main__":
    main()

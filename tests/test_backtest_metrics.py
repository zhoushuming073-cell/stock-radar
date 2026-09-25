import numpy as np
import pandas as pd

from radar.backtest.metrics import summarize_backtest


def test_equity_and_trade_metrics_from_known_curve():
    days = pd.bdate_range("2025-01-01", periods=3)
    equity = pd.DataFrame({"date": days, "equity": [100., 110., 90.],
                           "cash": [100., 55., 90.], "positions": [0, 1, 0]})
    trades = pd.DataFrame({"net_pnl": [10., -20.], "net_return": [.1, -.2],
                           "holding_sessions": [1, 2],
                           "exit_reason": ["take_profit_close", "stop_loss_gap"],
                           "gross_pnl": [11., -18.], "buy_fee_total": [.2, .5],
                           "sell_fee_total": [.3, .5], "slippage_cost": [.5, 1.]})
    summary = summarize_backtest(equity, trades, 100.)
    assert summary["final_equity"] == 90
    assert summary["total_return"] == -.1
    assert np.isclose(summary["max_drawdown"], 90 / 110 - 1, atol=1e-6)
    assert summary["trade_count"] == 2
    assert summary["profit_factor"] == .5
    assert summary["max_concurrent_positions"] == 1
    assert summary["exit_reason_counts"]["stop_loss_gap"] == 1


def test_zero_trades_with_valid_empty_blotter():
    equity = pd.DataFrame({"date": [pd.Timestamp("2025-01-01")],
                           "equity": [100.], "cash": [100.], "positions": [0]})
    trades = pd.DataFrame(columns=["net_pnl", "net_return", "holding_sessions", "exit_reason",
                                   "gross_pnl", "buy_fee_total", "sell_fee_total", "slippage_cost"])
    summary = summarize_backtest(equity, trades, 100.)
    assert summary["trade_count"] == 0
    assert summary["total_return"] == 0
    assert summary["max_drawdown"] == 0

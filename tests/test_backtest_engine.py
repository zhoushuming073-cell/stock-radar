from pathlib import Path

import numpy as np
import pandas as pd

from radar.backtest.costs import load_fee_config
from radar.backtest.engine import BacktestConfig, run_backtest
from radar.strategy.ranking import CandidateRules


FEES = load_fee_config(Path(__file__).parents[1] / "config" / "research.yaml")
RULES = CandidateRules(80, -.10, 3)


def market(entry_close=100, next_open=100, next_close=100, after_open=100,
           after_close=100, n=12):
    days = list(pd.bdate_range("2025-01-01", periods=n))
    rows = []
    for index, day in enumerate(days):
        opening = 100 if index == 0 else next_open if index == 1 else after_open if index == 2 else 100
        closing = entry_close if index == 0 else next_close if index == 1 else after_close if index == 2 else 100
        rows.append({"date": day, "symbol": "A", "open": opening, "close": closing,
                     "avg_dollar_volume_20": 1e9, "elasticity_score": 90.,
                     "drawdown_20": -.15, "ret_1": .01, "close_location": .8,
                     "tradability_pass": True, "security_name": "A Inc"})
    frame = pd.DataFrame(rows).set_index(["date", "symbol"], drop=False)
    return days, frame


def run(days, frame, *, slippage=0):
    cfg = BacktestConfig(slippage_bps=slippage, max_position_fraction=1.0,
                         max_order_to_avg_dollar_volume=1.0)
    return run_backtest(frame, days, signal_start=days[0], signal_end=days[0],
                        evaluation_end=days[10], rules=RULES,
                        fee_config=FEES, config=cfg)


def test_next_open_entry_and_entry_day_close_take_profit():
    days, frame = market(next_open=100, next_close=106)
    result = run(days, frame)
    trade = result.trades.iloc[0]
    assert trade.entry_date == days[1]
    assert trade.exit_date == days[1]
    assert trade.exit_reason == "take_profit_close"
    assert trade.holding_sessions == 1


def test_entry_day_close_stop_and_high_low_not_required():
    days, frame = market(next_open=100, next_close=89)
    result = run(days, frame)
    assert result.trades.iloc[0].exit_reason == "stop_loss_close"
    assert not {"high", "low"}.intersection(frame.columns)


def test_intraday_high_low_do_not_trigger_exits():
    days, frame = market(next_open=100, next_close=103)
    frame["high"] = 108
    frame["low"] = 88
    trade = run(days, frame).trades.iloc[0]
    assert trade.exit_reason == "max_holding_period"


def test_entry_open_is_not_a_pre_entry_target_check():
    days, frame = market(next_open=116, next_close=116)
    result = run_backtest(
        frame, days, signal_start=days[0], signal_end=days[0],
        evaluation_end=days[10], rules=RULES, fee_config=FEES,
        config=BacktestConfig(slippage_bps=0, entry_gap_max=.20,
                              max_position_fraction=1.0,
                              max_order_to_avg_dollar_volume=1.0))
    assert result.trades.iloc[0].entry_reference == 116
    assert result.trades.iloc[0].exit_reason != "take_profit_gap"


def test_gap_exit_realizes_actual_open_above_target():
    days, frame = market(next_open=100, next_close=100, after_open=116)
    trade = run(days, frame).trades.iloc[0]
    assert trade.exit_reason == "take_profit_gap"
    assert trade.exit_reference == 116
    assert trade.exit_date == days[2]


def test_gap_exit_realizes_actual_open_below_stop():
    days, frame = market(next_open=100, next_close=100, after_open=84)
    trade = run(days, frame).trades.iloc[0]
    assert trade.exit_reason == "stop_loss_gap"
    assert trade.exit_reference == 84


def test_no_threshold_for_ten_sessions_forces_close_exit():
    days, frame = market()
    trade = run(days, frame).trades.iloc[0]
    assert trade.exit_reason == "max_holding_period"
    assert trade.holding_sessions == 10
    assert trade.exit_date == days[10]


def test_fees_slippage_and_cash_reconcile():
    days, frame = market(next_close=106)
    result = run(days, frame, slippage=20)
    trade = result.trades.iloc[0]
    assert trade.entry_execution > trade.entry_reference
    assert trade.exit_execution < trade.exit_reference
    assert trade.buy_fee_total > 0 and trade.sell_fee_total > 0
    assert np.isclose(trade.net_pnl, trade.gross_pnl - trade.buy_fee_total -
                      trade.sell_fee_total - trade.slippage_cost)
    assert np.isclose(result.equity.iloc[-1].equity,
                      1_000_000 + result.trades.net_pnl.sum())
    assert result.equity.cash.min() >= 0


def test_held_symbol_not_reentered_and_open_exit_funds_next_entry():
    days, frame = market(n=13)
    extra = frame.copy().reset_index(drop=True)
    extra["symbol"] = "B"
    extra["security_name"] = "B Inc"
    extra["elasticity_score"] = [10.] + [90.] * (len(extra) - 1)
    frame = pd.concat([frame.reset_index(drop=True), extra]).set_index(["date", "symbol"], drop=False)
    frame.loc[(days[2], "A"), "open"] = 116
    result = run_backtest(
        frame, days, signal_start=days[0], signal_end=days[1],
        evaluation_end=days[11], rules=RULES, fee_config=FEES,
        config=BacktestConfig(slippage_bps=0, max_position_fraction=1.0,
                              max_order_to_avg_dollar_volume=1.0))
    entered = result.orders.loc[result.orders.status == "entered"]
    assert entered.symbol.tolist() == ["A", "B"]
    assert entered.date.tolist() == [days[1], days[2]]
    assert result.equity.cash.min() >= 0


def test_gap_gate_can_leave_cash_idle():
    days, frame = market(next_open=106)
    result = run(days, frame)
    assert result.trades.empty
    assert result.orders.iloc[0].status == "gap_rejected"
    assert result.equity.equity.eq(1_000_000).all()

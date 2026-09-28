"""Daily Open/Close portfolio simulator for the confirmed Strategy 2 contract.

Signals are computed at each close and can enter only at the next market Open.
High and Low are deliberately absent from the input required by this engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import floor, isfinite
from typing import Callable

import pandas as pd

from radar.backtest.costs import FeeConfig, buy_cost, sell_cost
from radar.backtest.metrics import TRADE_COLUMNS
from radar.strategy.ranking import CandidateRules, rank_candidates


@dataclass(frozen=True)
class BacktestConfig:
    initial_capital: float = 1_000_000.0
    take_profit: float | None = 0.05
    stop_loss: float | None = -0.10
    max_holding_sessions: int | None = 10
    entry_gap_min: float = -0.10
    entry_gap_max: float = 0.05
    max_position_fraction: float = 1 / 3
    minimum_position_fraction: float = 0.01
    max_order_to_avg_dollar_volume: float = 0.02
    slippage_bps: float = 10.0
    allocator: str = "equal_cash"
    candidate_variant: str = "combined_rank"
    market_guard: str = "none"
    execution_timing: str = "next_open"
    fail_on_missing_marks: bool = False

    def __post_init__(self) -> None:
        if (self.initial_capital <= 0
                or (self.take_profit is not None and not 0 < self.take_profit)
                or (self.stop_loss is not None and not -1 < self.stop_loss < 0)):
            raise ValueError("invalid capital or exit thresholds")
        if ((self.max_holding_sessions is not None and self.max_holding_sessions < 1)
                or self.entry_gap_min >= self.entry_gap_max):
            raise ValueError("invalid holding period or gap limits")
        if not 0 < self.max_position_fraction <= 1 or not 0 <= self.minimum_position_fraction <= self.max_position_fraction:
            raise ValueError("invalid position fractions")
        if not 0 < self.max_order_to_avg_dollar_volume <= 1 or self.slippage_bps < 0:
            raise ValueError("invalid participation or slippage")
        if self.allocator not in {"equal_cash", "strategy_score", "strategy_times_elasticity"}:
            raise ValueError("unknown allocator")
        if self.market_guard not in {"none", "spy_ma200"}:
            raise ValueError("unknown market guard")
        if self.execution_timing not in {"legacy_close", "next_open"}:
            raise ValueError("unknown execution timing")


@dataclass
class Position:
    symbol: str
    quantity: int
    entry_date: pd.Timestamp
    entry_index: int
    signal_date: pd.Timestamp
    entry_reference: float
    entry_execution: float
    entry_total: float
    buy_fee_total: float
    buy_commission: float
    buy_platform: float
    buy_settlement: float
    buy_cat: float
    buy_slippage_cost: float
    strategy2_score: float
    elasticity_score: float
    drawdown_20: float
    entry_gap: float
    last_close: float

    @property
    def cost_basis(self) -> float:
        return self.entry_total / self.quantity


@dataclass
class BacktestResult:
    equity: pd.DataFrame
    trades: pd.DataFrame
    orders: pd.DataFrame
    open_positions: list[Position]


class BacktestCancelled(Exception):
    """A local research run was cancelled between trading sessions."""


def _price(row: pd.Series | None, column: str) -> float | None:
    if row is None:
        return None
    value = row.get(column)
    if value is None or not isfinite(float(value)) or float(value) <= 0:
        return None
    return float(value)


def _allocation_weights(candidates: list[dict], allocator: str) -> list[float]:
    if allocator == "equal_cash":
        raw = [1.0] * len(candidates)
    elif allocator == "strategy_score":
        raw = [max(float(item["strategy2_score"]), 0.0) for item in candidates]
    else:
        raw = [max(float(item["strategy2_score"]), 0.0) *
               max(float(item["elasticity_score"]), 0.0) for item in candidates]
    total = sum(raw)
    return [value / total for value in raw] if total > 0 else [0.0] * len(raw)


def run_backtest(
    bars_and_features: pd.DataFrame,
    sessions: list[pd.Timestamp],
    *, signal_start: pd.Timestamp,
    signal_end: pd.Timestamp,
    evaluation_end: pd.Timestamp,
    rules: CandidateRules,
    fee_config: FeeConfig,
    config: BacktestConfig = BacktestConfig(),
    market_ok: dict[pd.Timestamp, bool] | None = None,
    candidate_selector: Callable[[pd.DataFrame, set[str]], pd.DataFrame] | None = None,
    progress_callback: Callable[[dict], None] | None = None,
    cancel_requested: Callable[[], bool] | None = None,
) -> BacktestResult:
    """Run one chronological segment from its first signal date through exits.

    The input index is (date, symbol). Required market fields are Open and Close
    only. ``evaluation_end`` includes a holding-period tail after the final
    signal. Positions remaining after that date are reported, never fabricated
    as closed trades.
    """
    if not isinstance(bars_and_features.index, pd.MultiIndex) or bars_and_features.index.names != ["date", "symbol"]:
        raise ValueError("bars_and_features must have MultiIndex (date, symbol)")
    sessions = [pd.Timestamp(day) for day in sessions]
    signal_start, signal_end, evaluation_end = (pd.Timestamp(day) for day in
                                               (signal_start, signal_end, evaluation_end))
    if sessions != sorted(set(sessions)) or signal_start not in sessions or signal_end not in sessions or evaluation_end not in sessions:
        raise ValueError("sessions must be sorted unique market dates covering segment bounds")
    start_idx, signal_end_idx, end_idx = (sessions.index(pd.Timestamp(day)) for day in
                                         (signal_start, signal_end, evaluation_end))
    if not start_idx <= signal_end_idx < end_idx:
        raise ValueError("signal window must end before the evaluation tail")
    missing = {"open", "close", "avg_dollar_volume_20", "symbol", "elasticity_score",
               "drawdown_20", "ret_1", "close_location", "tradability_pass", "security_name"} - set(bars_and_features.columns)
    if missing:
        raise ValueError(f"missing backtest fields: {sorted(missing)}")
    if config.market_guard != "none" and market_ok is None:
        raise ValueError("market guard requires a causal market_ok series")
    slip = config.slippage_bps / 10_000
    cash = float(config.initial_capital)
    positions: dict[str, Position] = {}
    pending_exits: dict[str, str] = {}
    pending: list[dict] = []
    trade_rows: list[dict] = []
    order_rows: list[dict] = []
    equity_rows: list[dict] = []
    peak_equity = float(config.initial_capital)

    def exit_position(position: Position, day: pd.Timestamp, reference: float,
                      reason: str, holding_sessions: int) -> None:
        nonlocal cash
        execution = reference * (1 - slip)
        fees = sell_cost(execution, position.quantity, fee_config)
        proceeds = position.quantity * execution - fees.total
        cash += proceeds
        gross_pnl = position.quantity * (reference - position.entry_reference)
        sell_slippage = position.quantity * (reference - execution)
        slippage_cost = position.buy_slippage_cost + sell_slippage
        net_pnl = proceeds - position.entry_total
        trade_rows.append({
            "symbol": position.symbol, "signal_date": position.signal_date,
            "entry_date": position.entry_date, "exit_date": day,
            "entry_reference": position.entry_reference,
            "entry_execution": position.entry_execution,
            "exit_reference": reference, "exit_execution": execution,
            "quantity": position.quantity, "entry_gap": position.entry_gap,
            "strategy2_score": position.strategy2_score,
            "elasticity_score": position.elasticity_score,
            "drawdown_20": position.drawdown_20,
            "entry_total": position.entry_total, "exit_proceeds": proceeds,
            "gross_pnl": gross_pnl, "buy_fee_total": position.buy_fee_total,
            "sell_fee_total": fees.total,
            "commission": position.buy_commission + fees.commission,
            "platform": position.buy_platform + fees.platform,
            "settlement": position.buy_settlement + fees.settlement,
            "sec": fees.sec, "finra": fees.finra,
            "cat": position.buy_cat + fees.cat,
            "slippage_cost": slippage_cost, "net_pnl": net_pnl,
            "net_return": net_pnl / position.entry_total,
            "holding_sessions": holding_sessions, "exit_reason": reason,
        })
        del positions[position.symbol]

    for idx in range(start_idx, end_idx + 1):
        if cancel_requested is not None and cancel_requested():
            raise BacktestCancelled("backtest cancelled by user")
        day = sessions[idx]
        trade_count_before = len(trade_rows)
        order_count_before = len(order_rows)
        try:
            daily = bars_and_features.xs(day, level="date", drop_level=True)
        except KeyError:
            daily = pd.DataFrame(columns=bars_and_features.columns)
        if not daily.empty and "symbol" in daily.columns:
            daily = daily.set_index("symbol", drop=False)

        def row_for(symbol: str) -> pd.Series | None:
            if daily.empty or symbol not in daily.index:
                return None
            row = daily.loc[symbol]
            if isinstance(row, pd.DataFrame):
                raise ValueError(f"duplicate bar for {symbol} on {day.date()}")
            return row

        if config.fail_on_missing_marks:
            missing = [symbol for symbol in positions
                       if row_for(symbol) is None or _price(row_for(symbol), "close") is None]
            if missing:
                raise ValueError(
                    f"open PIT position has no eligible price on {day.date()}: {missing}; "
                    "delisting or missing data requires an explicit policy")

        # Carried positions get first claim on the market Open. Their proceeds
        # can fund today's entries, but positions cannot be sold pre-entry.
        for position in list(positions.values()):
            opening = _price(row_for(position.symbol), "open")
            if opening is None:
                continue
            queued_reason = pending_exits.pop(position.symbol, None)
            if queued_reason is not None:
                exit_position(position, day, opening, queued_reason,
                              idx - position.entry_index + 1)
                continue
            move = opening / position.cost_basis - 1
            if config.take_profit is not None and move >= config.take_profit:
                exit_position(position, day, opening, "take_profit_gap", idx - position.entry_index + 1)
            elif config.stop_loss is not None and move <= config.stop_loss:
                exit_position(position, day, opening, "stop_loss_gap", idx - position.entry_index + 1)

        executable: list[dict] = []
        for candidate in pending:
            symbol = candidate["symbol"]
            if symbol in positions:
                order_rows.append({"date": day, "symbol": symbol, "status": "already_held"})
                continue
            current = row_for(symbol)
            opening = _price(current, "open")
            closing = _price(current, "close")
            if opening is None or (config.execution_timing == "legacy_close" and closing is None):
                order_rows.append({"date": day, "symbol": symbol, "status": "missing_entry_bar"})
                continue
            gap = opening / candidate["signal_close"] - 1
            if not config.entry_gap_min <= gap <= config.entry_gap_max:
                order_rows.append({"date": day, "symbol": symbol, "status": "gap_rejected", "gap": gap})
                continue
            executable.append({**candidate, "entry_reference": opening, "entry_gap": gap})
        pending = []

        if executable:
            open_equity = cash + sum(
                p.quantity * (_price(row_for(p.symbol), "open") or p.last_close)
                for p in positions.values())
            available_cash = cash
            weights = _allocation_weights(executable, config.allocator)
            for candidate, weight in zip(executable, weights):
                symbol = candidate["symbol"]
                reference = candidate["entry_reference"]
                execution = reference * (1 + slip)
                liquidity_cap = candidate["avg_dollar_volume_20"] * config.max_order_to_avg_dollar_volume
                budget = min(available_cash * weight, open_equity * config.max_position_fraction,
                             liquidity_cap)
                quantity = floor(budget / execution)
                total = 0.0
                while quantity > 0:
                    fees = buy_cost(execution, quantity, fee_config)
                    total = quantity * execution + fees.total
                    if total <= budget + 1e-9 and total <= cash + 1e-9:
                        break
                    quantity -= 1
                if quantity < 1 or total < open_equity * config.minimum_position_fraction:
                    order_rows.append({"date": day, "symbol": symbol, "status": "allocation_too_small"})
                    continue
                cash -= total
                if cash < -1e-7:
                    raise AssertionError("cash became negative after entry")
                cash = max(cash, 0.0)
                positions[symbol] = Position(
                    symbol=symbol, quantity=quantity, entry_date=day, entry_index=idx,
                    signal_date=candidate["signal_date"], entry_reference=reference,
                    entry_execution=execution, entry_total=total,
                    buy_fee_total=fees.total, buy_commission=fees.commission,
                    buy_platform=fees.platform, buy_settlement=fees.settlement,
                    buy_cat=fees.cat, buy_slippage_cost=quantity * (execution - reference),
                    strategy2_score=candidate["strategy2_score"],
                    elasticity_score=candidate["elasticity_score"],
                    drawdown_20=candidate["drawdown_20"], entry_gap=candidate["entry_gap"],
                    last_close=_price(row_for(symbol), "close") or reference,
                )
                order_rows.append({"date": day, "symbol": symbol, "status": "entered",
                                   "gap": candidate["entry_gap"], "quantity": quantity,
                                   "cost": total})

        # At Close, evaluate executable exits before producing tomorrow's list.
        missing_marks = 0
        for position in list(positions.values()):
            closing = _price(row_for(position.symbol), "close")
            if closing is None:
                missing_marks += 1
                continue
            position.last_close = closing
            move = closing / position.cost_basis - 1
            holding_sessions = idx - position.entry_index + 1
            if config.execution_timing == "next_open":
                if position.symbol not in pending_exits:
                    if config.take_profit is not None and move >= config.take_profit:
                        pending_exits[position.symbol] = "take_profit_signal_next_open"
                    elif config.stop_loss is not None and move <= config.stop_loss:
                        pending_exits[position.symbol] = "stop_loss_signal_next_open"
                    elif (config.max_holding_sessions is not None
                          and holding_sessions >= config.max_holding_sessions):
                        pending_exits[position.symbol] = "max_holding_signal_next_open"
            elif config.take_profit is not None and move >= config.take_profit:
                exit_position(position, day, closing, "take_profit_close", holding_sessions)
            elif config.stop_loss is not None and move <= config.stop_loss:
                exit_position(position, day, closing, "stop_loss_close", holding_sessions)
            elif (config.max_holding_sessions is not None
                  and holding_sessions >= config.max_holding_sessions):
                exit_position(position, day, closing, "max_holding_period", holding_sessions)

        equity = cash + sum(p.quantity * p.last_close for p in positions.values())
        if equity < -1e-7:
            raise AssertionError("portfolio equity became negative")
        equity_rows.append({"date": day, "cash": cash, "equity": equity,
                            "positions": len(positions), "gross_exposure": equity - cash,
                            "missing_marks": missing_marks})
        peak_equity = max(peak_equity, equity)
        allowed_by_market = config.market_guard == "none" or bool(market_ok.get(day, False))
        if idx <= signal_end_idx and not daily.empty and allowed_by_market:
            selected = (candidate_selector(daily, set(positions))
                        if candidate_selector is not None
                        else rank_candidates(daily, rules, variant=config.candidate_variant,
                                             already_held=set(positions)))
            pending = [{"symbol": row.symbol, "signal_date": day,
                        "signal_close": float(row.close),
                        "strategy2_score": float(row.strategy2_score),
                        "elasticity_score": float(row.elasticity_score),
                        "drawdown_20": float(row.drawdown_20),
                        "avg_dollar_volume_20": float(row.avg_dollar_volume_20)}
                       for row in selected.itertuples(index=False)]
        if progress_callback is not None:
            progress_callback({
                "date": day,
                "completed_sessions": idx - start_idx + 1,
                "total_sessions": end_idx - start_idx + 1,
                "equity": equity,
                "cash": cash,
                "gross_exposure": equity - cash,
                "drawdown": equity / peak_equity - 1,
                "open_positions": [
                    {"symbol": p.symbol, "quantity": p.quantity,
                     "entry_date": p.entry_date, "entry_total": p.entry_total,
                     "entry_execution": p.entry_execution,
                     "cost_basis": p.cost_basis,
                     "last_close": p.last_close,
                     "unrealized_pnl": p.quantity * p.last_close - p.entry_total}
                    for p in positions.values()
                ],
                "closed_trades": len(trade_rows),
                "new_trades": trade_rows[trade_count_before:],
                "new_orders": order_rows[order_count_before:],
                "latest_signals": [dict(candidate) for candidate in pending],
            })
    trades = pd.DataFrame(trade_rows)
    if trades.empty:
        trades = pd.DataFrame(columns=list(TRADE_COLUMNS))
    return BacktestResult(pd.DataFrame(equity_rows), trades,
                          pd.DataFrame(order_rows), list(positions.values()))

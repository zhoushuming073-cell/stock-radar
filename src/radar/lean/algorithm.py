"""Generic LEAN execution policy. Reads frozen signals, never strategy code.

Runs inside LEAN's embedded Python, so only the standard library and LEAN are
imported. Portfolio cash, holdings, fills and fees belong to LEAN exclusively.
"""
from AlgorithmImports import *
import hashlib
import json
import math
from pathlib import Path
import time as wall_time


def fee_components(schedule, quantity, price, sell=False):
    notional = quantity * price
    out = {}
    for name in ('commission', 'platform', 'settlement'):
        out[name] = round(min(max(quantity * schedule[name + '_per_share'], schedule[name + '_min']),
                              notional * schedule[name + '_cap_notional_fraction']), 6)
    out['sec'] = round(max(notional * schedule['sec_sell_notional_fraction'], schedule['sec_sell_min']), 6) if sell else 0.0
    out['finra'] = round(min(max(quantity * schedule['finra_sell_per_share'], schedule['finra_sell_min']),
                             schedule['finra_sell_max']), 6) if sell else 0.0
    out['cat'] = round(max(quantity * schedule['cat_per_share'], schedule['cat_min']), 6)
    out['total'] = round(sum(out.values()), 6)
    return out


class ConfiguredFeeModel(FeeModel):
    def __init__(self, schedule, slippage):
        self.schedule = schedule
        self.slippage = slippage

    def get_order_fee(self, parameters):
        quantity = float(parameters.order.quantity)
        # This integration submits only MarketOrders against flat Open proxies.
        price = float(parameters.security.price) * (1 + self.slippage * (1 if quantity > 0 else -1))
        total = fee_components(self.schedule, abs(quantity), price, quantity < 0)['total']
        return OrderFee(CashAmount(total, 'USD'))


class StockRadarExecution(QCAlgorithm):
    def initialize(self):
        path = Path(self.get_parameter('stock-radar-manifest'))
        if hashlib.sha256(path.read_bytes()).hexdigest() != self.get_parameter('stock-radar-manifest-hash'):
            raise ValueError('Frozen LEAN manifest changed before initialization')
        self._sr_bundle = json.loads(path.read_text(encoding='utf-8'))
        self._sr_output = path.parent
        signals_path = Path(self._sr_bundle['signals_path'])
        if hashlib.sha256(signals_path.read_bytes()).hexdigest() != self._sr_bundle['signal_snapshot']:
            raise ValueError('Frozen signal snapshot changed')
        self._sr_sessions = self._sr_bundle['sessions']
        self._sr_day_index = {day: idx for idx, day in enumerate(self._sr_sessions)}
        self._sr_execution = self._sr_bundle['execution']
        if self._sr_execution['execution_timing'] != 'next_open':
            raise ValueError('LEAN only supports causal next-session Open execution')
        self._sr_signals = {}
        for row in json.loads(signals_path.read_text(encoding='utf-8'))['signals']:
            self._sr_signals.setdefault(row['signal_date'], []).append(row)
        for rows in self._sr_signals.values():
            rows.sort(key=lambda s: (s['rank'], s['symbol']))
        first, last = [datetime.strptime(d, '%Y-%m-%d') for d in (self._sr_sessions[0], self._sr_sessions[-1])]
        self.set_start_date(first.year, first.month, first.day)
        self.set_end_date(last.year, last.month, last.day)
        self.set_time_zone(TimeZones.NEW_YORK)
        self._sr_initial = float(self._sr_execution['initial_capital'])
        self.set_cash(self._sr_initial)
        self.set_brokerage_model(DefaultBrokerageModel(AccountType.MARGIN))
        self.settings.free_portfolio_value_percentage = 0
        self._sr_symbols = {}
        self._sr_slip = float(self._sr_execution['slippage_bps']) / 10000
        for ticker in self._sr_bundle['symbols']:
            security = self.add_equity(ticker, Resolution.MINUTE, fill_forward=False,
                                       data_normalization_mode=DataNormalizationMode.RAW)
            security.set_leverage(1)
            security.set_fee_model(ConfiguredFeeModel(self._sr_bundle['fees'], self._sr_slip))
            security.set_slippage_model(ConstantSlippageModel(self._sr_slip))
            security.set_fill_model(ImmediateFillModel())
            security.set_settlement_model(ImmediateSettlementModel())
            self._sr_symbols[ticker] = security.symbol
        self.set_benchmark(self._sr_symbols['SPY'])
        self._sr_entries = {}  # Annotations of native fills; never a shadow cash ledger.
        self._sr_context = {}
        self._sr_pending = []
        self._sr_exits = {}
        self._sr_orders_today = []
        self._sr_trades_today = []
        self._sr_trade_count = 0
        self._sr_peak = self._sr_initial
        self._sr_benchmark_start = None
        self._sr_observed_days = []

    def append(self, filename, row):
        with (self._sr_output / filename).open('a', encoding='utf-8') as stream:
            stream.write(json.dumps(row, allow_nan=False) + '\n')

    def submit(self, ticker, quantity, reference, reason, signal=None):
        self._sr_context[ticker] = {'reference': reference, 'reason': reason, 'signal': signal}
        ticket = self.market_order(self._sr_symbols[ticker], quantity, asynchronous=False, tag=reason)
        if ticket.status != OrderStatus.FILLED:
            raise ValueError(f'Native LEAN order was not filled: {ticker} {ticket.status}')

    def on_order_event(self, event):
        if event.status != OrderStatus.FILLED:
            return
        ticker = event.symbol.value
        context = self._sr_context[ticker]
        quantity, price = float(event.fill_quantity), float(event.fill_price)
        fee = float(event.order_fee.value.amount)
        stamp = event.utc_time.isoformat()
        day = self.time.strftime('%Y-%m-%d')
        order = self.transactions.get_order_by_id(event.order_id)
        row = {'order_id': event.order_id, 'symbol': ticker, 'order_time': order.time.isoformat(),
               'fill_time': stamp, 'date': day, 'direction': 'buy' if quantity > 0 else 'sell',
               'quantity': abs(quantity), 'reference_price': context['reference'], 'fill_price': price,
               'fees': fee, 'status': 'filled', 'reason': context['reason']}
        self.append('fills.jsonl', row)
        self._sr_orders_today.append(row)
        if quantity > 0:
            signal = context['signal']
            self._sr_entries[ticker] = {'symbol': ticker, 'quantity': quantity, 'entry_time': stamp,
                                    'entry_date': day, 'entry_execution': price, 'entry_reference': context['reference'],
                                    'entry_fee': fee, 'entry_total': quantity * price + fee,
                                    'signal_date': signal['signal_date'], 'strategy_score': signal['strategy_score'],
                                    'entry_index': self._sr_day_index[day]}
        else:
            entry = self._sr_entries.pop(ticker)
            proceeds = abs(quantity) * price - fee
            pnl = proceeds - entry['entry_total']
            trade = {**{k: v for k, v in entry.items() if k != 'entry_index'},
                     'exit_time': stamp, 'exit_date': day, 'exit_reference': context['reference'],
                     'exit_execution': price, 'exit_fee': fee, 'fees': entry['entry_fee'] + fee,
                     'exit_proceeds': proceeds, 'net_pnl': pnl, 'net_return': pnl / entry['entry_total'],
                     'holding_sessions': self._sr_day_index[day] - entry['entry_index'] + 1,
                     'exit_reason': context['reason']}
            self.append('trades.jsonl', trade)
            self._sr_trades_today.append(trade)
            self._sr_trade_count += 1
        self._sr_context.pop(ticker, None)

    def reason(self, move, held=None, gap=False):
        policy = self._sr_execution['exit']
        if policy['take_profit'] is not None and move >= policy['take_profit']:
            return 'take_profit_gap' if gap else 'take_profit'
        if policy['stop_loss'] is not None and move <= policy['stop_loss']:
            return 'stop_loss_gap' if gap else 'stop_loss'
        if held is not None and policy['max_holding_sessions'] is not None and held >= policy['max_holding_sessions']:
            return 'max_holding'
        return None

    def on_data(self, data):
        if not data.bars.contains_key(self._sr_symbols['SPY']):
            return
        day = self.time.strftime('%Y-%m-%d')
        if day not in self._sr_day_index:
            return
        bars = {ticker: data.bars[symbol] for ticker, symbol in self._sr_symbols.items()
                if data.bars.contains_key(symbol)}
        if self.time.hour == 9:
            self.open_session(day, bars)
        else:
            self.close_session(day, bars)

    def open_session(self, day, bars):
        self._sr_orders_today, self._sr_trades_today = [], []
        for ticker, entry in list(self._sr_entries.items()):
            if ticker not in bars:
                if self._sr_bundle['run_metadata'].get('universe_mode') == 'point_in_time':
                    raise ValueError(f'PIT held security has no Open: {day} {ticker}')
                continue
            reference = float(bars[ticker].open)
            move = reference / (entry['entry_total'] / entry['quantity']) - 1
            reason = self._sr_exits.get(ticker) or self.reason(move, gap=True)
            if reason:
                self.submit(ticker, -entry['quantity'], reference, reason)
                self._sr_exits.pop(ticker, None)
        eligible = []
        gap_policy = self._sr_execution['entry_gap']
        for signal in self._sr_pending:
            ticker = signal['symbol']
            if ticker in self._sr_entries or ticker not in bars:
                continue
            if signal['signal_date'] >= day:
                raise ValueError('Same-session/future signal reached execution')
            reference = float(bars[ticker].open)
            gap = reference / signal['reference_close'] - 1
            if gap_policy['enabled'] and not gap_policy['min'] <= gap <= gap_policy['max']:
                continue
            eligible.append((signal, reference))
        self._sr_pending = []
        eligible = eligible[:max(0, self._sr_bundle['max_positions'] - len(self._sr_entries))]
        total_weight = sum(s['allocation_weight'] for s, _ in eligible)
        available_cash = float(self.portfolio.cash)
        open_equity = float(self.portfolio.total_portfolio_value)
        sizing = self._sr_execution['sizing']
        for signal, reference in eligible:
            if len(self._sr_entries) >= self._sr_bundle['max_positions']:
                break
            weight = signal['allocation_weight'] / total_weight if total_weight > 0 else 1 / len(eligible)
            budget = min(available_cash * weight, open_equity * sizing['max_position_fraction'],
                         signal['avg_dollar_volume_20'] * self._sr_execution['liquidity']['max_adv_participation'])
            price = reference * (1 + self._sr_slip)
            quantity = math.floor(budget / price)
            while quantity > 0:
                cost = quantity * price + fee_components(self._sr_bundle['fees'], quantity, price)['total']
                if cost <= min(budget, float(self.portfolio.cash)):
                    break
                quantity -= 1
            if quantity <= 0 or quantity * price < open_equity * sizing['min_position_fraction']:
                continue
            self.submit(signal['symbol'], quantity, reference, 'signal_entry', signal)

    def close_session(self, day, bars):
        if day in self._sr_observed_days:
            raise ValueError('Multiple close observations in one session')
        positions = []
        for ticker, entry in self._sr_entries.items():
            if ticker not in bars and self._sr_bundle['run_metadata'].get('universe_mode') == 'point_in_time':
                raise ValueError(f'PIT held security has no Close: {day} {ticker}')
            security = self.securities[self._sr_symbols[ticker]]
            last = float(security.price)
            holding = self.portfolio[self._sr_symbols[ticker]]
            move = last / (entry['entry_total'] / entry['quantity']) - 1
            reason = self.reason(move, self._sr_day_index[day] - entry['entry_index'] + 1)
            if reason:
                self._sr_exits[ticker] = reason
            positions.append({**{k: v for k, v in entry.items() if k != 'entry_index'},
                              'last_close': last, 'last_price': last, 'cost_basis': entry['entry_total'] / entry['quantity'],
                              'quantity': float(holding.quantity),
                              'unrealized_pnl': float(holding.holdings_value) - entry['entry_total']})
        candidates = self._sr_signals.get(day, []) if self._sr_bundle['market_allowed'].get(day, False) else []
        self._sr_pending = [s for s in candidates if s['symbol'] not in self._sr_entries][
            :int(self._sr_execution['max_new_positions_per_day'])]
        equity, cash = float(self.portfolio.total_portfolio_value), float(self.portfolio.cash)
        self._sr_peak = max(self._sr_peak, equity)
        spy = float(bars['SPY'].close)
        if self._sr_benchmark_start is None:
            self._sr_benchmark_start = spy
        self._sr_observed_days.append(day)
        row = {'timestamp': self.utc_time.isoformat(), 'date': day,
               'completed_sessions': len(self._sr_observed_days), 'total_sessions': len(self._sr_sessions),
               'equity': equity, 'cash': cash, 'holdings_value': float(self.portfolio.total_holdings_value),
               'gross_exposure': float(self.portfolio.total_holdings_value),
               'benchmark': self._sr_initial * spy / self._sr_benchmark_start,
               'drawdown': equity / self._sr_peak - 1, 'open_positions': positions,
               'closed_trades': self._sr_trade_count, 'new_trades': self._sr_trades_today,
               'new_orders': self._sr_orders_today, 'latest_signals': self._sr_pending}
        self.append('daily.jsonl', row)
        if self._sr_bundle['pace_ms']:
            wall_time.sleep(self._sr_bundle['pace_ms'] / 1000)

    def on_end_of_algorithm(self):
        (self._sr_output / 'completed.json').write_text(json.dumps({
            'sessions': self._sr_observed_days, 'equity': float(self.portfolio.total_portfolio_value),
            'cash': float(self.portfolio.cash), 'total_fees': float(self.portfolio.total_fees)}), encoding='utf-8')

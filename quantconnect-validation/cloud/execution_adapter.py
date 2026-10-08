"""Cloud data/fill transport around the generated local execution policy."""
from AlgorithmImports import *
from datetime import datetime
from decimal import Decimal
from qc_input import INPUT, RUN
import qc_execution_source as execution_source
from qc_protocol import receipt_lines, digest
fee_components = execution_source.fee_components


class ReferenceOpenFee(FeeModel):
    def __init__(self, algorithm):
        self.algorithm = algorithm

    def get_order_fee(self, parameters):
        a = self.algorithm
        key = a.key_for_symbol(parameters.security.symbol)
        q = float(parameters.order.quantity)
        reference = (a._sr_context[key]['reference'] if key in a._sr_context else float(parameters.security.price))
        price = reference * (1 + a._sr_slip * (1 if q > 0 else -1))
        fee = fee_components(a._sr_bundle['fees'], abs(q), price, q < 0)['total']
        return OrderFee(CashAmount(Decimal(str(fee)), 'USD'))


class ReferenceOpenFill(ImmediateFillModel):
    def __init__(self, algorithm):
        self.algorithm = algorithm

    def market_fill(self, asset, order):
        event = super().market_fill(asset, order)
        if event.status == OrderStatus.FILLED:
            a = self.algorithm
            key = a.key_for_symbol(asset.symbol)
            # Benchmark fill convention: observed 09:30 minute Open, delivered at 09:31.
            # No constructed market bars and no backdated order timestamps.
            if key in a._sr_context:
                reference = a._sr_context[key]['reference']
                event.fill_price = Decimal(str(reference * (1 + a._sr_slip * (1 if order.quantity > 0 else -1))))
        return event


class StockRadarFrozenSignalCloud(execution_source.StockRadarExecution):
    def initialize(self):
        self.set_name('SRQC-' + RUN['id'])
        if not INPUT['prerequisite_smoke_verified'] or not INPUT['identity_bindings_verified']:
            raise ValueError('Real smoke and dated SID bindings required; no ticker-only execution')
        sids = [b['qc_sid'] for b in INPUT['bindings'].values()]
        if len(sids) != len(set(sids)):
            raise ValueError('Multiple local episodes share a QC SID; explicit alias review required')
        self._sr_bundle = INPUT['bundle']
        self._sr_sessions = self._sr_bundle['sessions']
        self._sr_day_index = {day: i for i, day in enumerate(self._sr_sessions)}
        self._sr_execution = self._sr_bundle['execution']
        self._sr_initial = float(self._sr_execution['initial_capital'])
        first, last = [datetime.fromisoformat(d) for d in (self._sr_sessions[0], self._sr_sessions[-1])]
        self.set_start_date(first.year, first.month, first.day)
        self.set_end_date(last.year, last.month, last.day)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.set_cash(self._sr_initial)
        self.set_brokerage_model(DefaultBrokerageModel(AccountType.MARGIN))
        self.settings.free_portfolio_value_percentage = 0
        self._sr_slip = float(self._sr_execution['slippage_bps']) / 10000
        self._sr_symbols = {}
        self._sr_signals = {}
        for row in INPUT['signals']:
            signal = {**row, 'symbol': row['security_id']}
            self._sr_signals.setdefault(row['signal_date'], []).append(signal)
        for rows in self._sr_signals.values():
            rows.sort(key=lambda s: (s['rank'], s['historical_ticker']))
        for uid, binding in INPUT['bindings'].items():
            symbol = Symbol(SecurityIdentifier.parse(binding['qc_sid']), binding['historical_ticker'])
            security = self.add_security(symbol, Resolution.MINUTE, fill_forward=False,
                                       data_normalization_mode=DataNormalizationMode.RAW)
            if str(security.symbol.id) != binding['qc_sid']:
                raise ValueError('Cloud native SID differs from frozen binding')
            security.set_leverage(1)
            security.set_fee_model(ReferenceOpenFee(self))
            security.set_fill_model(ReferenceOpenFill(self))
            security.set_settlement_model(ImmediateSettlementModel())
            self._sr_symbols[uid] = security.symbol
        self._sr_symbols['SPY'] = self.add_equity('SPY', Resolution.MINUTE, fill_forward=False,
            data_normalization_mode=DataNormalizationMode.RAW).symbol
        self.set_benchmark(self._sr_symbols['SPY'])
        self._sr_pit = {'cloud_native_actions': True}
        self._sr_entries, self._sr_context, self._sr_exits = {}, {}, {}
        self._sr_pending, self._sr_orders_today, self._sr_trades_today = [], [], []
        self._sr_trade_count, self._sr_peak = 0, self._sr_initial
        self._sr_benchmark_start = None
        self._sr_observed_days = []
        self._records = {'fills.jsonl': [], 'trades.jsonl': [], 'actions.jsonl': []}
        self._equity_sum, self._drawdown = 0., 0.
        self._turnover = 0.
        self._open_seen = set()

    def on_data(self, data):
        day = self.time.strftime('%Y-%m-%d')
        if day not in self._sr_day_index or not data.bars.contains_key(self._sr_symbols['SPY']):
            return
        bars = {key: data.bars[symbol] for key, symbol in self._sr_symbols.items()
                if data.bars.contains_key(symbol) and not data.bars[symbol].is_fill_forward}
        if self.time.hour == 9 and self.time.minute == 31 and day not in self._open_seen:
            if any(b.time.hour != 9 or b.time.minute != 30 for b in bars.values()):
                raise ValueError('First minute Open semantics differ')
            self._open_seen.add(day)
            self.open_session(day, bars)
        spy_hours = self.securities[self._sr_symbols['SPY']].exchange.hours
        close = spy_hours.get_next_market_close(datetime.fromisoformat(day), False)
        if self.time == close:
            self.close_session(day, bars)

    def append(self, filename, row):
        if filename == 'daily.jsonl':
            self._equity_sum += row['equity']
            self._drawdown = min(self._drawdown, row['drawdown'])
            self.plot('SRQC Portfolio', 'Equity', row['equity'])
            self.plot('SRQC Portfolio', 'Benchmark', row['benchmark'])
            return
        self._records[filename].append(row)
        if filename == 'fills.jsonl':
            self._turnover += row['quantity'] * row['fill_price']

    def on_dividends(self, dividends):
        for dividend in dividends.values():
            key = self.key_for_symbol(dividend.symbol)
            quantity = float(self.portfolio[dividend.symbol].quantity)
            if quantity:
                self.append('actions.jsonl', {'event_type': 'dividend', 'symbol': key,
                    'date': self.time.strftime('%Y-%m-%d'), 'distribution': float(dividend.distribution),
                    'quantity': quantity, 'native_cash': float(self.portfolio.cash)})

    def on_delistings(self, delistings):
        for event in delistings.values():
            self.append('actions.jsonl', {'event_type': 'delisting', 'symbol': self.key_for_symbol(event.symbol),
                'date': self.time.strftime('%Y-%m-%d'), 'kind': str(event.type)})

    def on_order_event(self, event):
        if event.status == OrderStatus.FILLED:
            key = self.key_for_symbol(event.symbol)
            if key not in self._sr_context:
                # Native delisting liquidation is a disclosed model difference, never a fake payout.
                if key not in self._sr_entries or event.fill_quantity >= 0:
                    raise ValueError('Unbound native order fill')
                self._sr_context[key] = {'reference': float(event.fill_price),
                                         'reason': 'qc_native_liquidation', 'signal': None}
        super().on_order_event(event)

    def on_end_of_algorithm(self):
        trades = self._records['trades.jsonl']
        equity = float(self.portfolio.total_portfolio_value)
        metrics = {'trade_count': len(trades), 'win_rate': sum(t['net_return'] > 0 for t in trades) / len(trades) if trades else None,
            'average_trade': sum(t['net_return'] for t in trades) / len(trades) if trades else None,
            'final_equity': equity, 'total_return': equity / self._sr_initial - 1,
            'max_drawdown': self._drawdown, 'fees': float(self.portfolio.total_fees),
            'turnover': self._turnover / (self._equity_sum / len(self._sr_observed_days)) if self._sr_observed_days else None,
            'remaining_holdings': len(self._sr_entries)}
        actions = [{k: v for k, v in row.items() if k in {'event_type', 'symbol', 'date', 'old_symbol', 'new_symbol', 'kind'}}
                   for row in self._records['actions.jsonl']]
        record = {'type': 'execution', 'signal_hash': INPUT['signal_hash'], 'metrics': metrics,
            'fills_count': len(self._records['fills.jsonl']), 'fills_hash': digest(self._records['fills.jsonl']),
            'trades_hash': digest(trades), 'actions': actions, 'actions_hash': digest(self._records['actions.jsonl']),
            'sessions_count': len(self._sr_observed_days), 'sessions_hash': digest(self._sr_observed_days),
            'model_differences': ['Open benchmark fill at 09:31 delivery; order time is not backdated',
                'Native minute holdings marks affect sizing versus local flat Open proxy',
                'Native splits/dividends/delistings; no local corporate cash settlement override',
                'Source trade return convention excludes ordinary dividends; native portfolio includes them']}
        if RUN['layer'] == 'layer3-detail':
            bucket = RUN['bucket']
            record = {'type': 'execution_details', 'bucket': bucket, 'buckets': 128,
                'signal_hash': INPUT['signal_hash'], 'fills_hash': record['fills_hash'],
                'trades_hash': record['trades_hash'], 'sessions_count': record['sessions_count'],
                'sessions_hash': record['sessions_hash'],
                'fills': [[n, row] for n, row in enumerate(self._records['fills.jsonl']) if n % 128 == bucket],
                'trades': [[n, row] for n, row in enumerate(trades) if n % 128 == bucket]}
        for line in receipt_lines(RUN, [record], 'PARTIAL'):
            self.log(line)

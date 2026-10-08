from AlgorithmImports import *
from datetime import datetime, timedelta

# The generator inlines protocol.py and a frozen RUN before this class.
class StockRadarCloudSmoke(QCAlgorithm):
    def initialize(self):
        self.set_name('SRQC-' + RUN['id'])
        first, last = (datetime.fromisoformat(d) for d in RUN['dates'])
        self.set_start_date(first.year, first.month, first.day)
        self.set_end_date(last.year, last.month, last.day)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.settings.daily_precise_end_time = True
        self.set_cash(1000000)
        self.universe_settings.resolution = Resolution.DAILY
        self._universe = self.add_universe(lambda _: Universe.UNCHANGED)
        tickers = ['SPY', 'MSFT', RUN['case']]
        self._symbols = {}
        for ticker in tickers:
            # String subscriptions resolve today's reused ticker, not the historical issuer.
            sid = SecurityIdentifier.generate_equity(ticker, Market.USA, mapping_resolve_date=first)
            symbol = Symbol(sid, ticker)
            self._symbols[ticker] = self.add_security(symbol, Resolution.DAILY, fill_forward=False,
                data_normalization_mode=DataNormalizationMode.RAW).symbol
        self._seen = {str(s.id): set() for s in self._symbols.values()}
        self._mapping = []
        self._splits = []

    def on_data(self, data):
        for symbol in self._symbols.values():
            if not data.bars.contains_key(symbol):
                continue
            bar = data.bars[symbol]
            sid = str(symbol.id)
            if sid in self._seen and not bar.is_fill_forward and bar.close > 0:
                self._seen[sid].add(str(bar.end_time.date()))

    def on_symbol_changed_events(self, events):
        for event in events.values():
            self._mapping.append([str(event.symbol.id), event.old_symbol, event.new_symbol,
                                  self.time.strftime('%Y-%m-%d')])

    def on_splits(self, splits):
        for split in splits.values():
            if split.type == SplitType.SPLIT_OCCURRED:
                self._splits.append([str(split.symbol.id), self.time.strftime('%Y-%m-%d'),
                                     float(split.split_factor)])

    def on_end_of_algorithm(self):
        case = self._symbols[RUN['case']]
        master_ok, split_history_ok, history_ok = False, False, False
        try:
            frames = raw_frames(self, [case, self._symbols['MSFT']], RUN['dates'][0], self.time)
            history_ok = all(len(frame) >= 3 for frame in frames.values())
            universe_history = self.history(self._universe, 1, Resolution.DAILY)
            for _, fundamentals in universe_history.items():
                for f in fundamentals:
                    if f.symbol.id == case.id:
                        master_ok = (bool(normalize_cik(f.company_reference.cik)) and
                                     str(f.security_reference.security_type) == 'ST00000001')
            splits = list(self.history[Split](case, datetime.fromisoformat(RUN['dates'][0]), self.time))
            split_history_ok = (RUN['case'] == 'FB' or any(
                s.type == SplitType.SPLIT_OCCURRED and abs(float(s.split_factor) - .1) < 1e-10
                for s in splits))
        except Exception as error:
            # Error type only: never print dataset rows or credential-bearing exceptions.
            self._api_error = type(error).__name__
        mapping_ok = (RUN['case'] != 'FB' or any(
            e[0] == str(case.id) and e[1] == 'FB' and e[2] == 'META' and e[3] == '2022-06-09'
            for e in self._mapping))
        split_ok = (RUN['case'] != 'NVDA' or any(
            e[0] == str(case.id) and e[1] == '2024-06-10' and abs(e[2] - .1) < 1e-10
            for e in self._splits))
        checks = {'history_access': history_ok,
                  'stable_control': all(len(v) >= 3 for v in self._seen.values()),
                  'security_master': master_ok, 'mapping': mapping_ok,
                  'split_history': split_ok and split_history_ok}
        record = {'type': 'smoke', 'checks': checks, 'case': RUN['case'],
                  'sid': str(case.id), 'observed_sessions': sorted(self._seen[str(case.id)]),
                  'mapping_events': self._mapping, 'split_events': self._splits,
                  'api_error_type': getattr(self, '_api_error', None)}
        status = 'PASS' if all(checks.values()) else 'FAIL'
        for line in receipt_lines(RUN, [record], status):
            self.log(line)
        # Cloud Debug is capped at 200 characters; keep full receipts in Log.
        self.debug('SRQC_SMOKE ' + canonical({'case': RUN['case'], 'checks': checks, 'status': status}))

from AlgorithmImports import *
from datetime import datetime
from qc_input import INPUT, RUN
from qc_protocol import receipt_lines
from qc_membership import population_from_objects, independent_core, compare_membership, membership_details


class StockRadarDataValidation(QCAlgorithm):
    def initialize(self):
        self.set_name('SRQC-' + RUN['id'])
        if not INPUT['prerequisite_smoke_verified']:
            raise ValueError('Import BOTH real Cloud smoke PASS receipts before staging this project')
        day = datetime.fromisoformat(RUN['dates'][0])
        self.set_start_date(day.year, day.month, day.day)
        self.set_end_date(day.year, day.month, day.day)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.settings.daily_precise_end_time = True
        self.set_cash(INPUT['execution']['initial_capital'])
        self.universe_settings.resolution = Resolution.DAILY
        self._population = []
        self._records = []
        self._benchmarks = {t: self.add_equity(t, Resolution.DAILY, fill_forward=False,
                            data_normalization_mode=DataNormalizationMode.RAW).symbol for t in ['SPY', 'QQQ']}
        self._universe = self.add_universe(self.capture_population)

    def capture_population(self, fundamentals):
        day = self.time.strftime('%Y-%m-%d')
        if day in RUN['dates']:
            self._population = population_from_objects(fundamentals, day)
        return []  # History only; thousands of live subscriptions would exceed Free memory.

    def on_data(self, data):
        day = self.time.strftime('%Y-%m-%d')
        if self._records or day not in RUN['dates'] or not data.bars.contains_key(self._benchmarks['SPY']):
            return
        if not self._population or any(p['as_of'] != day for p in self._population):
            raise ValueError('Missing dated QC population; no current fallback')
        core = independent_core(self, self._population, day, INPUT['core_rules'], INPUT['feature_start'])
        local = INPUT['local'][day]
        record, bridge = compare_membership(self._population, core, local, day)
        if RUN['layer'] == 'layer1-detail':
            self._records.append(membership_details(self._population, core, local, day, RUN['bucket']))
        elif RUN['layer'] == 'layer1':
            self._records.append(record)
        elif RUN['layer'] == 'layer2':
            from qc_strategy_adapter import qc_candidates, compare_candidates
            candidates, count = qc_candidates(self, self._population, core, day, INPUT)
            self._records.append(compare_candidates(candidates, self._population, local, day, count))
        else:
            raise ValueError('Unexpected validation layer')

    def on_end_of_algorithm(self):
        complete = len(self._records) == len(RUN['dates'])
        # External observation alone never certifies local PIT readiness.
        status = 'PARTIAL' if complete else 'FAIL'
        for line in receipt_lines(RUN, self._records, status):
            self.log(line)

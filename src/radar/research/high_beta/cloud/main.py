"""Cloud host: source-generated Stock Radar selector -> native LEAN policy.

No selection formulas here. QC market data and private candidate snapshots stay
in Cloud; only normal backtest statistics and aggregate diagnostics are logged.
"""
from AlgorithmImports import *
from datetime import datetime
from collections import Counter
import json
import pandas as pd
from sr_config import STUDY,SETTINGS,EXECUTION,FEES,RECEIPT
from sr_q2 import Settings,analyze,beta,rank,candidate
from sr_sessions import calendar
from sr_data import (QcEvidence,population,history_frames,split_events,
                     causal_split_window,complete_amount)
from sr_execution import StockRadarExecution,fee_components
from sr_fill import ReferenceOpenFee,ReferenceOpenFill


class StockRadarQ2V12Cloud(StockRadarExecution):
    def initialize(self):
        self.set_name(STUDY['experiment'])
        first=datetime.fromisoformat(STUDY['start']);last=datetime.fromisoformat(STUDY['end'])
        self.set_start_date(first.year,first.month,first.day);self.set_end_date(last.year,last.month,last.day)
        self.set_time_zone(TimeZones.NEW_YORK);self.set_cash(EXECUTION['initial_capital'])
        self.settings.daily_precise_end_time=True
        self.set_brokerage_model(DefaultBrokerageModel(AccountType.MARGIN))
        self.settings.free_portfolio_value_percentage=0
        self.universe_settings.resolution=Resolution.DAILY
        self._universe=self.add_universe(lambda _:Universe.UNCHANGED)
        self._benchmarks={s:self.add_equity(s,Resolution.MINUTE,fill_forward=False,
            data_normalization_mode=DataNormalizationMode.RAW).symbol for s in ['SPY','QQQ']}
        self._sr_sessions=[str(d.date()) for d in calendar().sessions_in_range(first,last)]
        self._sr_day_index={d:i for i,d in enumerate(self._sr_sessions)}
        self._sr_execution=EXECUTION;self._sr_initial=float(EXECUTION['initial_capital'])
        self._sr_fixed_close=True;self._sr_slip=EXECUTION['slippage_bps']/10000
        self._sr_bundle={'fees':FEES,'max_positions':EXECUTION['max_positions'],
            'pace_ms':0,'run_metadata':{'universe_mode':'point_in_time'},'market_allowed':{}}
        self._sr_symbols={'SPY':self._benchmarks['SPY']};self._sr_signals={}
        self._sr_entries={};self._sr_context={};self._sr_pending=[];self._sr_exits={}
        self._sr_orders_today=[];self._sr_trades_today=[];self._sr_trade_count=0
        self._sr_peak=self._sr_initial;self._sr_benchmark_start=None;self._sr_observed_days=[]
        self._sr_pit={'cloud_native_actions':True}
        self._records={'fills.jsonl':[],'trades.jsonl':[],'actions.jsonl':[]}
        self._years={};self._open_seen=set();self._cfg=Settings(**SETTINGS)
        self.set_benchmark(self._benchmarks['SPY'])
        self.schedule.on(self.date_rules.every_day(self._benchmarks['SPY']),
                         self.time_rules.before_market_open(self._benchmarks['SPY'],60),self.select_prior_close)
        self.debug('Q2 v1.2 QC-native exploratory; source '+RECEIPT['selector_sha256'][:16])

    def select_prior_close(self):
        # At08:30 D, consume only fixed OHLCV and identity through previous T.
        current=pd.Timestamp(self.time.date());cal=calendar()
        day=cal.date_to_session(current-pd.Timedelta(days=1),direction='previous')
        text=str(day.date());all_days=cal.sessions_in_range('2020-01-01',day)
        if text<STUDY['start']:return
        index=self._sr_day_index[str(current.date())]
        if index>len(self._sr_sessions)-EXECUTION['exit']['max_holding_sessions']:
            return  # leave enough sessions for the registered fixed-horizon exit
        year=str(day.year);counts=self._years.setdefault(year,Counter());counts['signal_days']+=1
        symbols=population(self,self._universe,text);counts['common_security_days']+=len(symbols)
        recent=history_frames(self,symbols,all_days[-20].to_pydatetime(),self.time)
        liquid=[]
        for symbol in symbols:
            amount=complete_amount(recent[str(symbol.id)],all_days[-20:])
            if amount is None:counts['missing_recent_market']+=1
            elif amount>=self._cfg.adv20_minimum:liquid.append(symbol)
        counts['liquidity_qualified']+=len(liquid)
        first=all_days[-min(len(all_days),127)].to_pydatetime()
        refs=history_frames(self,list(self._benchmarks.values()),first,self.time)
        def adjusted(symbol,raw,start):
            return causal_split_window(raw,split_events(self,symbol,start,self.time),text)
        spy=adjusted(self._benchmarks['SPY'],refs[str(self._benchmarks['SPY'].id)],first)
        qqq=adjusted(self._benchmarks['QQQ'],refs[str(self._benchmarks['QQQ'].id)],first)
        if list(spy.date)!=list(all_days[-127:]):raise ValueError('Incomplete mandatory QC SPY window')
        small=history_frames(self,liquid,first,self.time);market=[]
        for symbol in liquid:
            x=adjusted(symbol,small[str(symbol.id)],first)
            b=beta(x.set_index('date').close.reindex(all_days[-127:]),spy.set_index('date').close,
                   126,self._cfg.beta_min_samples_126,self._cfg)
            if b['value'] is not None and not b['outliers'] and b['value']>=self._cfg.beta_minimum:market.append(symbol)
        counts['joint_market_gates']+=len(market)
        start=all_days[-min(len(all_days),STUDY['feature_sessions'])].to_pydatetime()
        wide=history_frames(self,market,start,self.time);rows=[]
        for symbol in market:
            x=adjusted(symbol,wide[str(symbol.id)],start)
            # Original market/channel/day formulas; QC evidence is a separate domain.
            result=analyze(x,text,spy,qqq,QcEvidence(True,True,True),self._cfg)
            if result['market'] is not None:
                result['market']['amount_definition']='QC native close * volume, causal joint split basis; not exact intraday notional'
            if not result['market_qualified']:
                counts['full_window_rejected']+=1
            if result['structure_qualified']:counts['structure_qualified']+=1
            if result['near_support']:counts['near_support']+=1
            if result['watch']:counts['watch']+=1
            if result['qualified']:counts['early_reversal']+=1
            if not result['qualified']:continue
            rows.append(candidate(result,security_id=str(symbol.id),symbol=symbol.value))
        by_id={str(s.id):s for s in market};signals=[]
        for row in rank(rows)[:STUDY['top_k']]:
            sid=row.security_id;symbol=by_id[sid]
            if sid not in self._sr_symbols:
                security=self.add_security(symbol,Resolution.MINUTE,fill_forward=False,
                    data_normalization_mode=DataNormalizationMode.RAW)
                if str(security.symbol.id)!=sid:raise ValueError('Native SID substitution')
                security.set_leverage(1);security.set_fee_model(ReferenceOpenFee(self))
                security.set_slippage_model(ConstantSlippageModel(self._sr_slip))
                security.set_fill_model(ReferenceOpenFill(self));security.set_settlement_model(ImmediateSettlementModel())
                self._sr_symbols[sid]=security.symbol
            raw=wide[sid];analysis=row.window_metadata['analysis']
            signals.append(dict(symbol=sid,signal_date=text,rank=row.rank,strategy_score=row.score,
                strategy_id='q2',strategy_version=row.version,reference_close=float(raw.close.iloc[-1]),
                avg_dollar_volume_20=analysis['market']['adv20_dollar'],allocation_weight=1))
        if any(s['signal_date']>=str(current.date()) for s in signals):raise ValueError('Noncausal Cloud signal')
        self._sr_signals[text]=signals;self._sr_pending=signals
        counts['selected_signals']+=len(signals)
        # Keep just held/pending subscriptions; never unsubscribe an open position.
        keep={s['symbol'] for s in signals}|set(self._sr_entries)|{'SPY'}
        for sid,symbol in list(self._sr_symbols.items()):
            if sid not in keep and not self.transactions.get_open_orders(symbol):
                self.remove_security(symbol);self._sr_symbols.pop(sid)

    def on_data(self,data):
        day=self.time.strftime('%Y-%m-%d')
        if day not in self._sr_day_index or not data.bars.contains_key(self._sr_symbols['SPY']):return
        bars={sid:data.bars[s] for sid,s in self._sr_symbols.items() if data.bars.contains_key(s) and not data.bars[s].is_fill_forward}
        if self.time.hour==9 and self.time.minute==31 and day not in self._open_seen:
            if any(b.time.hour!=9 or b.time.minute!=30 for b in bars.values()):raise ValueError('Open minute timestamp changed')
            self._open_seen.add(day);self.open_session(day,bars)
        hours=self.securities[self._sr_symbols['SPY']].exchange.hours
        if self.time==hours.get_next_market_close(datetime.fromisoformat(day),False):self.close_session(day,bars)

    def append(self,filename,row):
        if filename=='daily.jsonl':
            self.plot('SR Q2 v1.2','Equity',row['equity']);self.plot('SR Q2 v1.2','Drawdown',row['drawdown'])
            return
        self._records[filename].append(row)  # no RAW bars/reference corpus exported

    def on_order_event(self,event):
        if event.status==OrderStatus.FILLED:
            key=self.key_for_symbol(event.symbol)
            if key not in self._sr_context:
                if key not in self._sr_entries or event.fill_quantity>=0:raise ValueError('Unbound native liquidation')
                self._sr_context[key]={'reference':float(event.fill_price),'reason':'qc_native_liquidation','signal':None}
        super().on_order_event(event)

    def on_end_of_algorithm(self):
        stats={'experiment':STUDY['experiment'],'selector_version':'high-beta-liquid-channel-v1.2',
            'source_receipt':RECEIPT['selector_sha256'],'scope':'exploratory_QC_native_not_local_SIP_or_Fresh',
            'sessions':len(self._sr_observed_days),'final_equity':float(self.portfolio.total_portfolio_value),
            'expected_sessions':len(self._sr_sessions),'full_calendar_observed':self._sr_observed_days==self._sr_sessions,
            'total_return':float(self.portfolio.total_portfolio_value)/self._sr_initial-1,
            'total_fees':float(self.portfolio.total_fees),'closed_trades':self._sr_trade_count,
            'remaining_holdings':len(self._sr_entries),'annual_funnel':self._years}
        message=json.dumps(stats,sort_keys=True,separators=(',',':'),allow_nan=False)
        if len(message.encode())>7000:raise ValueError('Aggregate log quota; do not truncate')
        self.log('SRQ2C '+message)

"""Contract guards and opt-in tests against the actual independent LEAN build."""
from dataclasses import replace
import json
import os
from pathlib import Path
from uuid import uuid4

import pandas as pd
import pytest

from radar.backtest.costs import load_fee_config, buy_cost, sell_cost
from radar.backtest.engine import BacktestConfig, BacktestCancelled, run_backtest
from radar.lab.parameters import execution_defaults_from_legacy
from radar.lean.contracts import Signal
from radar.lean.export import prepare_bundle
from radar.lean.runtime import installation, invoke, digest, verify_bundle
from radar.lean.result_adapter import normalize
from radar.strategy.ranking import CandidateRules

ROOT = Path(__file__).resolve().parents[1]


def fixture_inputs():
    sessions = pd.to_datetime(['2025-01-06', '2025-01-07', '2025-01-08', '2025-01-10', '2025-01-13', '2025-01-14'])
    prices = []
    paths = {'AAA': [(10, 10), (10.1, 11), (11.3, 11.2), (11, 11), (11, 10.8), (10.8, 10.8)],
             'BBB': [(20, 20), (20, 19), (18, 18), (18, 18), (18, 18), (18, 18)],
             'CCC': [(30, 30)] * 6, 'SPY': [(100 + i, 100 + i) for i in range(6)]}
    for symbol, rows in paths.items():
        for day, (opening, close) in zip(sessions, rows):
            prices.append({'date': day, 'symbol': symbol, 'open': opening, 'high': max(opening, close),
                           'low': min(opening, close), 'close': close, 'volume': 1000000,
                           'avg_dollar_volume_20': 10000000, 'elasticity_score': 100., 'drawdown_20': -.15,
                           'ret_1': 0., 'close_location': .5, 'tradability_pass': True, 'security_name': symbol})
    frame = pd.DataFrame(prices)
    signals = []
    for index, symbols in ((0, ['AAA', 'BBB']), (1, ['CCC']), (3, ['AAA'])):
        for rank, symbol in enumerate(symbols, 1):
            signals.append({'signal_date': str(sessions[index].date()), 'symbol': symbol, 'rank': rank,
                            'strategy_score': 10. - rank, 'strategy_id': 'golden', 'strategy_version': '1.0',
                            'reference_close': paths[symbol][index][1], 'avg_dollar_volume_20': 10000000.,
                            'allocation_weight': 1.})
    config = BacktestConfig(initial_capital=10000, max_position_fraction=.4,
                            minimum_position_fraction=0., max_holding_sessions=2,
                            take_profit=.05, stop_loss=-.08, slippage_bps=10)
    raw = {'initial_capital': config.initial_capital, 'max_new_candidates': 3,
           'take_profit': config.take_profit, 'stop_loss': config.stop_loss,
           'max_holding_sessions': config.max_holding_sessions,
           'entry_gap_min': config.entry_gap_min, 'entry_gap_max': config.entry_gap_max,
           'max_position_fraction': config.max_position_fraction,
           'minimum_position_fraction': config.minimum_position_fraction,
           'max_order_to_avg_dollar_volume': config.max_order_to_avg_dollar_volume,
           'allocator': config.allocator, 'market_guard': config.market_guard}
    execution = execution_defaults_from_legacy(raw, slippage_bps=10, execution_timing='next_open')
    metadata = {'strategy_id': 'golden', 'strategy_version': '1.0', 'universe_mode': 'current_snapshot',
                'window': [str(sessions[0].date()), str(sessions[-2].date()), str(sessions[-1].date())]}
    fees = load_fee_config(ROOT / 'config/research.yaml')
    return sessions, frame, signals, config, execution, metadata, fees


def test_signal_rejects_forward_data_and_unstamped_context():
    _, _, signals, *_ = fixture_inputs()
    row = signals[0]
    with pytest.raises(ValueError):
        Signal(**row, available_at='2025-01-06T16:00:00-05:00', forward_return_10=.5)
    with pytest.raises(ValueError):
        Signal(**row, available_at='2025-01-06T16:00:00')


def native_home():
    if os.environ.get('STOCK_RADAR_TEST_LEAN') != '1':
        pytest.skip('Set STOCK_RADAR_TEST_LEAN=1 to run the independent local native engine')
    return installation(ROOT)


def test_frozen_execution_manifest_and_price_files_cannot_drift(tmp_path):
    data = tmp_path / 'data'
    data.mkdir()
    price = data / 'price.csv'
    price.write_text('10000', encoding='utf-8')
    index = tmp_path / 'data-index.json'
    index.write_text(json.dumps({'price.csv': digest(price)}), encoding='utf-8')
    manifest = {}
    for filename, key in [('algorithm.py', 'algorithm_sha256'), ('signals.json', 'signal_snapshot'),
                          ('source-prices.csv', 'source_prices_sha256')]:
        path = tmp_path / filename
        path.write_text('frozen fixture', encoding='utf-8')
        manifest[key] = digest(path)
    manifest['data_snapshot'] = digest(index)
    path = tmp_path / 'manifest.json'
    path.write_text(json.dumps(manifest), encoding='utf-8')
    original = digest(path)
    verify_bundle(tmp_path, original)
    price.write_text('20000', encoding='utf-8')
    with pytest.raises(ValueError, match='data changed'):
        verify_bundle(tmp_path, original)
    price.write_text('10000', encoding='utf-8')
    path.write_text(json.dumps({**manifest, 'execution': 'changed'}), encoding='utf-8')
    with pytest.raises(ValueError, match='manifest changed'):
        verify_bundle(tmp_path, original)


@pytest.mark.parametrize('empty', [False, True])
def test_native_golden_parity(tmp_path, empty):
    home, identity = native_home()
    sessions, frame, signals, config, execution, metadata, fees = fixture_inputs()
    if empty:
        signals = []
    output = tmp_path / 'native'
    manifest = prepare_bundle(home, output, metadata, list(sessions), signals, frame, execution, fees)
    progress = []
    run_id = str(uuid4())
    raw = invoke(ROOT, output, manifest, run_id, progress.append, lambda: False, identity)
    normalized, metrics = normalize(output, raw, identity)

    def selector(daily, held):
        day = str(pd.Timestamp(daily['date'].iloc[0]).date())
        chosen = [r for r in signals if r['signal_date'] == day and r['symbol'] not in held]
        rows = daily.set_index('symbol', drop=False).reindex([r['symbol'] for r in chosen]).copy()
        rows['strategy2_score'] = [r['strategy_score'] for r in chosen]
        return rows.reset_index(drop=True)

    legacy = run_backtest(frame.set_index(['date', 'symbol'], drop=False), sessions,
                          signal_start=sessions[0], signal_end=sessions[-2], evaluation_end=sessions[-1],
                          rules=CandidateRules(elasticity_min=0, drawdown_20_max=0, max_new=3),
                          fee_config=fees, config=config, candidate_selector=selector)
    pd.testing.assert_series_equal(pd.Series([r['cash'] for r in normalized['equity']]),
                                   legacy.equity['cash'].reset_index(drop=True), check_names=False, atol=.0001)
    pd.testing.assert_series_equal(pd.Series([r['equity'] for r in normalized['equity']]),
                                   legacy.equity['equity'].reset_index(drop=True), check_names=False, atol=.0001)
    assert len(normalized['trades']) == len(legacy.trades)
    for actual, expected in zip(normalized['trades'], legacy.trades.to_dict('records')):
        for field in ('symbol', 'quantity', 'entry_execution', 'exit_execution', 'net_pnl', 'net_return'):
            if isinstance(expected[field], str):
                assert actual[field] == expected[field]
            else:
                assert actual[field] == pytest.approx(expected[field], abs=.0001)
        assert actual['entry_date'] == str(pd.Timestamp(expected['entry_date']).date())
        assert actual['exit_date'] == str(pd.Timestamp(expected['exit_date']).date())
        assert actual['entry_fee'] == pytest.approx(expected['buy_fee_total'], abs=.000001)
        assert actual['exit_fee'] == pytest.approx(expected['sell_fee_total'], abs=.000001)
        # The normalized LEAN tag is concise; legacy appends fill timing.
        assert actual['exit_reason'] == expected['exit_reason'].removesuffix('_signal_next_open')
    assert len(progress) == len(sessions)
    assert all(o['date'] > next(s['signal_date'] for s in signals if s['symbol'] == o['symbol'])
               for o in normalized['orders'] if o['direction'] == 'buy')
    # Every reported native fee matches the shared declared schedule.
    for order in normalized['orders']:
        calculate = buy_cost if order['direction'] == 'buy' else sell_cost
        assert order['fees'] == pytest.approx(calculate(order['fill_price'], order['quantity'], fees).total)
    assert metrics['cagr'] is None  # Do not annualize a six-day fixture as a real estimate.
    evidence = {'identity': identity, 'case': 'empty' if empty else 'tp-sl-hold-reentry-cash',
                'metrics': metrics, 'native_output': str(output), 'status': 'passed'}
    artifact = ROOT / 'data/strategy-lab/lean-validation'
    artifact.mkdir(parents=True, exist_ok=True)
    (artifact / f'golden-{empty}.json').write_text(json.dumps(evidence, indent=2), encoding='utf-8')
    broken = json.loads(raw.read_text(encoding='utf-8-sig'))
    final_point = broken['charts']['Strategy Equity']['series']['Equity']['values'][-1]
    if isinstance(final_point, list):
        final_point[-1] = 1
    else:
        final_point['close'] = 1
    raw.write_text(json.dumps(broken), encoding='utf-8')
    with pytest.raises(ValueError, match='reconcile'):
        normalize(output, raw, identity)


def test_native_cancellation_stops_child(tmp_path):
    home, identity = native_home()
    sessions, frame, signals, _, execution, metadata, fees = fixture_inputs()
    output = tmp_path / 'cancelled'
    manifest = prepare_bundle(home, output, metadata, list(sessions), signals, frame, execution, fees)
    with pytest.raises(BacktestCancelled):
        invoke(ROOT, output, manifest, str(uuid4()), lambda s: None, lambda: True, identity)

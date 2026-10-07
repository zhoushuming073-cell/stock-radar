"""LEAN raw evidence -> Stock Radar schema. Frontends never read QC internals."""
from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from radar.lean.contracts import PortfolioPoint, RESULT_SCHEMA_VERSION
from radar.lean.runtime import digest


def journal(path):
    return [json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()] if path.exists() else []


def normalize(output: Path, raw_path: Path, identity: dict) -> tuple[dict, dict]:
    manifest = json.loads((output / 'manifest.json').read_text(encoding='utf-8'))
    raw = json.loads(raw_path.read_text(encoding='utf-8-sig'))
    completed = json.loads((output / 'completed.json').read_text(encoding='utf-8'))
    daily = journal(output / 'daily.jsonl')
    if [r['date'] for r in daily] != manifest['sessions'] or completed['sessions'] != manifest['sessions']:
        raise ValueError('LEAN did not observe every requested trading session')
    if raw.get('errorMessage') or raw.get('runtimeError'):
        raise ValueError(f'LEAN runtime error: {raw.get("errorMessage") or raw.get("runtimeError")}')
    curve = []
    initial = manifest['execution']['initial_capital']
    peak = initial
    for row in daily:
        peak = max(peak, row['equity'])
        point = PortfolioPoint(**{**row, 'drawdown': row['equity'] / peak - 1}).model_dump(mode='json')
        point['positions'] = row['open_positions']
        point['gross_exposure'] = row['holdings_value']
        curve.append(point)
    if abs(curve[-1]['equity'] - completed['equity']) > .02:
        raise ValueError('LEAN final portfolio differs from daily journal')
    series = raw.get('charts', {}).get('Strategy Equity', {}).get('series', {}).get('Equity', {})
    values = series.get('values', [])
    if not values:
        raise ValueError('Native LEAN result has no authoritative equity series')
    point = values[-1]
    final = point[-1] if isinstance(point, list) else point.get('close', point.get('y'))
    if final is None or abs(float(final) - completed['equity']) > .02:
        raise ValueError('Native LEAN result equity does not reconcile with portfolio observations')
    orders = journal(output / 'fills.jsonl')
    actions = journal(output / 'actions.jsonl')
    if manifest.get('pit_dataset'):
        cash_from_fills = initial + sum((1 if row['direction'] == 'sell' else -1)
            * row['quantity'] * row['fill_price'] - row['fees'] for row in orders)
        for action in actions:
            if action['event_type'] == 'split':
                cash_from_fills += action.get('cash_in_lieu', 0)
            if action['event_type'] == 'cash_acquisition':
                if (abs(action['cash_after'] - action['cash_before'] - action['cash_entitlement']) > .000001
                        or action['holding_after'] != 0):
                    raise ValueError('Native terminal cash/holding does not reconcile')
                cash_from_fills += action['cash_entitlement']
        if abs(cash_from_fills - completed['cash']) > .02:
            raise ValueError('Native PIT cash does not reconcile with fills and corporate actions')
    total_fees = sum(row['fees'] for row in orders)
    if abs(total_fees - completed['total_fees']) > .0001:
        raise ValueError('LEAN fees do not reconcile with fill events')
    trades = []
    for row in journal(output / 'trades.jsonl'):
        trades.append({**row, 'entry_price': row['entry_execution'], 'exit_price': row['exit_execution'],
                       'pnl': row['net_pnl'], 'pnl_percentage': row['net_return'],
                       'buy_fee_total': row['entry_fee'], 'sell_fee_total': row['exit_fee'],
                       'gross_pnl': (row['net_pnl'] + row['entry_fee'] + row['exit_fee']
                                     if manifest.get('pit_dataset') else
                                     row['quantity'] * (row['exit_execution'] - row['entry_execution'])),
                       'slippage_cost': row['quantity'] * (
                           row['entry_execution'] - row['entry_reference'] + row['exit_reference'] - row['exit_execution'])})
    native_orders = raw.get('orders', {})
    for row in orders:
        order = native_orders.get(str(row['order_id']))
        sign = 1 if row['direction'] == 'buy' else -1
        if (order is None or float(order.get('quantity', 0)) != sign * row['quantity'] or
                order.get('status') != 3 or abs(float(order.get('price', 0)) - row['fill_price']) > .000001):
            raise ValueError('Fill journal does not match native LEAN orders')
    equity = pd.Series([initial, *[p['equity'] for p in curve]], dtype=float)
    returns = equity.pct_change().dropna()
    deviation = returns.std(ddof=1)
    downside = returns[returns < 0]
    wins = [t['net_pnl'] for t in trades if t['net_pnl'] > 0]
    losses = [t['net_pnl'] for t in trades if t['net_pnl'] < 0]
    n = len(curve)
    metrics = {
        'initial_capital': initial, 'final_equity': curve[-1]['equity'],
        'total_return': curve[-1]['equity'] / initial - 1,
        'cagr': (curve[-1]['equity'] / initial) ** (252 / n) - 1 if n >= 252 else None,
        'max_drawdown': min(p['drawdown'] for p in curve),
        'sharpe': float(returns.mean() / deviation * math.sqrt(252)) if n >= 2 and deviation > 0 else None,
        'sortino': float(returns.mean() / downside.std(ddof=1) * math.sqrt(252))
                   if len(downside) > 1 and downside.std(ddof=1) > 0 else None,
        'trade_count': len(trades), 'win_rate': len(wins) / len(trades) if trades else None,
        'average_win': sum(wins) / len(wins) if wins else None,
        'average_loss': sum(losses) / len(losses) if losses else None,
        'profit_factor': sum(wins) / -sum(losses) if losses else None,
        'turnover': sum(o['quantity'] * o['fill_price'] for o in orders) / equity.iloc[1:].mean(),
        'total_fees': total_fees, 'net_pnl': curve[-1]['equity'] - initial,
        'benchmark_return': curve[-1]['benchmark'] / initial - 1, 'sessions': n,
    }
    sources = {key: 'presentation analytics of LEAN native daily portfolio/fill observations'
               for key in metrics}
    sources['total_fees'] = 'LEAN Portfolio.TotalFees, reconciled to native OrderEvent fees'
    result = {'schema_version': RESULT_SCHEMA_VERSION, 'engine': 'lean',
              'run_metadata': {**manifest['run_metadata'], 'engine_identity': identity,
                               'signal_snapshot': manifest['signal_snapshot'],
                               'execution_data_snapshot': manifest['data_snapshot']},
              'equity': curve, 'trades': trades, 'orders': orders,
              'open_positions': daily[-1]['open_positions'], 'statistics': metrics,
              'statistic_sources': sources, 'native_statistics': raw.get('statistics', {}),
              'raw_result_path': str(raw_path), 'raw_result_sha256': digest(raw_path),
              'signal_snapshot': manifest['signal_snapshot'], 'signal_source': manifest['run_metadata'].get('source_scanner_run_id') or 'Stock Radar historical daily selection',
              'execution_data_snapshot': manifest['data_snapshot'],
              'execution_assumptions': {key: manifest[key] for key in (
                  'price_model', 'price_precision', 'price_basis', 'fill_model', 'settlement', 'limitations')}}
    if manifest.get('pit_dataset'):
        result['corporate_actions'] = actions
        sources['trade_count'] = 'native fills plus explicitly reconciled corporate-action entitlement closures; not LEAN TradeBuilder count'
        result['pit_execution_dataset'] = manifest['pit_dataset']
        preflight = manifest['run_metadata'].get('run_pit_readiness') or {}
        result['run_metadata']['run_pit_readiness'] = {**preflight,
            'scorecard': {**preflight.get('scorecard', {}), 'LEAN Native Execution': 'PASS',
                         'Result Reconciliation': 'PASS'}}
        for collection in (orders, trades, result['open_positions']):
            for row in collection:
                spec = manifest['pit_dataset']['securities'].get(row['symbol'])
                if spec:
                    row['security_id'] = spec['security_id']
    (output / 'normalized-result.json').write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    return result, metrics

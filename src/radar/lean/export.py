"""Freeze causal selection and local daily prices before starting LEAN."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import json
import math
from pathlib import Path
import shutil
import zipfile

import duckdb
import pandas as pd

from radar.lean.contracts import Signal, SIGNAL_SCHEMA_VERSION
from radar.lean.runtime import digest
from radar.strategy.adapter import evaluate_selection


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False), encoding='utf-8')


def freeze_signals(frame, sessions, metadata, plugin, store, execution, guard=None):
    """Only Stock Radar calls strategy code. No portfolio state enters selection."""
    source = metadata.get('source_scanner_run_id')
    by_day = {}
    if source:
        if not store.verify_scanner_artifacts(source):
            raise ValueError('Scanner snapshot failed verification')
        for row in store.get_scanner_candidates(source, limit=10_000_000):
            if row['selected']:
                by_day.setdefault(row['signal_date'], []).append(row)
    signals = []
    start, end, _ = metadata['window']
    allowed = {}
    method = execution['sizing']['method']
    for session in sessions:
        day = str(pd.Timestamp(session).date())
        market_ok = guard is None or bool(guard.get(pd.Timestamp(session), False))
        allowed[day] = market_ok
        if not start <= day <= end or not market_ok:
            continue
        try:
            daily = frame.xs(pd.Timestamp(session), level='date', drop_level=False)
        except KeyError:
            continue
        if source:
            chosen = sorted(by_day.get(day, []), key=lambda row: (row['rank'], row['symbol']))
        else:
            ranked, _ = evaluate_selection(plugin, metadata['config'], daily, set())
            chosen = ranked.loc[ranked['selected'], ['symbol', 'rank', 'strategy_score']].to_dict('records')
        lookup = daily.set_index('symbol', drop=False)
        for row in chosen:
            if row['symbol'] not in lookup.index:
                raise ValueError(f'Scanner candidate has no causal execution context: {day} {row["symbol"]}')
            context = lookup.loc[row['symbol']]
            score = float(row['strategy_score'])
            weight = (1.0 if method == 'equal_cash' else max(score, 0.0))
            if method == 'strategy_times_elasticity':
                weight *= max(float(context['elasticity_score']), 0.0)
            adv = float(context['avg_dollar_volume_20'])
            if not math.isfinite(adv):
                raise ValueError(f'Candidate ADV unavailable: {day} {row["symbol"]}')
            signals.append({'signal_date': day, 'symbol': row['symbol'],
                            'rank': int(row['rank']), 'strategy_score': score,
                            'strategy_id': metadata['strategy_id'],
                            'strategy_version': metadata['strategy_version'],
                            'reference_close': float(context['close']),
                            'avg_dollar_volume_20': adv, 'allocation_weight': weight})
    return signals, allowed


def prepare_bundle(home: Path, output: Path, metadata: dict, sessions: list,
                   signals: list[dict], prices: pd.DataFrame, execution: dict,
                   fees, allowed: dict | None = None, max_positions: int = 30,
                   *, pit_dataset: dict | None = None) -> Path:
    """Native LEAN Equity minute files contain two *daily-price proxy* observations.

    At 09:31 only that day's Open is visible. At the exchange close only Close
    becomes visible. These are not minute market data and simulate no intraday path.
    """
    output.mkdir(parents=True, exist_ok=False)
    data = output / 'data'
    references = ('market-hours/market-hours-database.json',
                  'symbol-properties/symbol-properties-database.csv')
    for relative in references:
        target = data / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(home / 'engine/Data' / relative, target)
    hours = json.loads((data / references[0]).read_text())['entries']['Equity-usa-[*]']
    holidays = {datetime.strptime(day, '%m/%d/%Y').date().isoformat() for day in hours['holidays']}
    early = {datetime.strptime(day, '%m/%d/%Y').date().isoformat(): time
             for day, time in hours.get('earlyCloses', {}).items()}
    days = [str(pd.Timestamp(day).date()) for day in sessions]
    if not days or days != sorted(set(days)):
        raise ValueError('sessions must be nonempty, unique and chronological')
    close_times = {}
    for day in days:
        if day in holidays or pd.Timestamp(day).weekday() > 4:
            raise ValueError(f'Source session is closed in LEAN exchange calendar: {day}')
        close_times[day] = early.get(day, '16:00:00')
    frozen = []
    for row in signals:
        day = row['signal_date']
        if day not in close_times or not metadata['window'][0] <= day <= metadata['window'][1]:
            raise ValueError('signal is outside the immutable signal interval')
        stamp = pd.Timestamp(f'{day} {close_times[day]}', tz='America/New_York').isoformat()
        frozen.append(Signal(**row, available_at=stamp).model_dump(mode='json'))
    if len({(s['signal_date'], s['symbol']) for s in frozen}) != len(frozen):
        raise ValueError('duplicate signal for one symbol/session')
    frozen.sort(key=lambda s: (s['signal_date'], s['rank'], s['symbol']))
    if any((row['strategy_id'], row['strategy_version']) != (
            metadata['strategy_id'], metadata['strategy_version']) for row in frozen):
        raise ValueError('signal strategy identity differs from run metadata')
    signal_file = output / 'signals.json'
    write_json(signal_file, {'schema_version': SIGNAL_SCHEMA_VERSION, 'signals': frozen})
    symbols = sorted({s['symbol'] for s in frozen} | {'SPY'})
    prices = prices.copy()
    prices['date'] = pd.to_datetime(prices['date']).dt.strftime('%Y-%m-%d')
    prices = prices[prices['symbol'].isin(symbols) & prices['date'].isin(days)]
    if prices.duplicated(['date', 'symbol']).any():
        raise ValueError('duplicate execution price')
    spy = prices.loc[prices['symbol'] == 'SPY'].set_index('date')
    if set(spy.index) != set(days):
        raise ValueError('Benchmark SPY must cover every execution session')
    # Preserve input OHLCV evidence. LEAN receives only isolated Open/Close proxies.
    prices = prices.sort_values(['date', 'symbol'])
    price_file = output / 'source-prices.csv'
    prices.to_csv(price_file, index=False)
    required = {symbol: set() for symbol in symbols}
    required['SPY'] = set(days)
    maximum_hold = execution['exit']['max_holding_sessions']
    for signal in frozen:
        index = days.index(signal['signal_date'])
        end = len(days) if maximum_hold is None else min(len(days), index + maximum_hold + 2)
        required[signal['symbol']].update(days[index + 1:end])
    for symbol in symbols:
        lower = symbol.lower()
        spec = (pit_dataset or {}).get('securities', {}).get(symbol)
        for kind, content in (('map_files', spec['maps'] if spec else f'19980102,{lower},P\n20501231,{lower},P\n'),
                              ('factor_files', spec['factors'] if spec else '19980102,1,1,1\n20501231,1,1,1\n')):
            folder = data / 'equity/usa' / kind
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f'{lower}.csv').write_text(content, encoding='ascii')
        folder = data / 'equity/usa/minute' / lower
        folder.mkdir(parents=True, exist_ok=True)
        subset = prices.loc[(prices['symbol'] == symbol) & prices['date'].isin(required[symbol])]
        for row in subset.to_dict('records'):
            mapped_lower = row.get('mapped_symbol', symbol).lower() if pit_dataset else lower
            folder = data / 'equity/usa/minute' / mapped_lower
            folder.mkdir(parents=True, exist_ok=True)
            day = row['date']
            close_seconds = pd.Timedelta(close_times[day]).total_seconds()
            lines = []
            for seconds, field in ((34200, 'open'), (close_seconds - 60, 'close')):
                price = float(row[field])
                if not math.isfinite(price) or price <= 0:
                    raise ValueError(f'Invalid {field} for {day} {symbol}')
                scaled = round(price * 10000)
                if scaled <= 0:
                    raise ValueError('Price below LEAN equity data precision')
                lines.append(f'{int(seconds * 1000)},{scaled},{scaled},{scaled},{scaled},1\n')
            stamp = day.replace('-', '')
            # Fixed ZIP timestamps make the exported data hash reproducible.
            with zipfile.ZipFile(folder / f'{stamp}_trade.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
                info = zipfile.ZipInfo(f'{stamp}_{mapped_lower}_minute_trade.csv', (2000, 1, 1, 0, 0, 0))
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, ''.join(lines))
    data_files = {str(p.relative_to(data)).replace('\\', '/'): digest(p)
                  for p in sorted(data.rglob('*')) if p.is_file()}
    data_index = output / 'data-index.json'
    write_json(data_index, data_files)
    algorithm = output / 'algorithm.py'
    adapter = ('algorithm_fixed_horizon.py' if execution['exit'].get('timing') == 'fixed_horizon_close'
               else 'algorithm.py')
    shutil.copy2(Path(__file__).with_name(adapter), algorithm)
    if metadata.get('engine_code_hash') and digest(algorithm) != metadata['engine_code_hash']:
        raise ValueError('LEAN execution adapter changed after queuing')
    manifest = {'schema_version': SIGNAL_SCHEMA_VERSION, 'run_metadata': metadata,
                'sessions': days, 'close_times': close_times, 'symbols': symbols,
                'signals_path': str(signal_file), 'signal_snapshot': digest(signal_file),
                'source_prices_sha256': digest(price_file), 'data_snapshot': digest(data_index),
                'reference_hashes': {p: digest(data / p) for p in references},
                'execution': execution, 'fees': asdict(fees), 'max_positions': max_positions,
                'market_allowed': allowed or {day: True for day in days},
                'pace_ms': metadata.get('pace_ms', 0),
                'price_model': 'daily_open_close_proxies', 'price_precision': .0001,
                'price_basis': 'source daily bars; Raw normalization; no additional split/dividend adjustment',
                'fill_model': 'LEAN ImmediateFillModel; open proxy observed at 09:31 ET',
                'settlement': 'immediate; cash-funded; leverage=1',
                'algorithm_sha256': digest(algorithm),
                'limitations': ['No intraday path or trigger ordering', 'No order book/partial-fill simulation',
                                'Universe and source-price adjustment biases remain those of the input snapshot']}
    if pit_dataset:
        # Actions, delisting/settlement inputs and full dependency hash are part
        # of the same manifest lock as maps, factors, prices and engine source.
        manifest['pit_dataset'] = {**pit_dataset, 'price_sha256': digest(price_file),
                                   'data_index_sha256': digest(data_index)}
        manifest['price_basis'] = 'raw execution; native holdings splits once; causal split-only features'
    path = output / 'manifest.json'
    write_json(path, manifest)
    return path


def load_prices(database: Path, start: str, end: str, symbols: list[str]) -> pd.DataFrame:
    with duckdb.connect(str(database), read_only=True) as connection:
        connection.register('requested_symbols', pd.DataFrame({'symbol': sorted(set(symbols) | {'SPY'})}))
        return connection.execute('''SELECT b.date, b.symbol, b.open, b.high, b.low, b.close, b.volume
            FROM daily_bars b JOIN requested_symbols s USING(symbol)
            WHERE b.date BETWEEN ? AND ? ORDER BY b.date, b.symbol''', [start, end]).df()

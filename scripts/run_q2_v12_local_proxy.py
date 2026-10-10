"""Q2 v1.2 bounded Shape Research proxy -> independent local Native LEAN.

The normal historical-certified Q2 evidence gate is not changed. This script
uses an explicit uncertified proxy domain after direct user authorization.
All selector parameters and execution rules remain the registered v1.2 values.
"""
from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import subprocess
from uuid import uuid4

import duckdb
import numpy as np
import pandas as pd
import yaml

from radar.backtest.costs import load_fee_config
from radar.lean.export import prepare_bundle
from radar.lean.result_adapter import normalize
from radar.lean.runtime import digest, installation, invoke
from radar.research.candidates import fingerprint
from radar.research.high_beta.channel import VERSION, analyze, candidate, rank, settings
from radar.research.historical_quant import long_prefix
from radar.research.infrastructure import ResearchInfrastructure
from radar.research.quant_lean import execution_config, execution_display, execution_inputs, publish_result
from radar.research.sessions import calendar, require_session

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'data/research/q2-v12-local-proxy'
CONFIG = ROOT / 'config/q2_v12_local_proxy.yaml'
SOURCE = 'legacy:alpaca:sip'


@dataclass(frozen=True)
class ProxyEvidence:
    """Separate research-only proof; never asserts historical certification."""

    scope: str = 'historical_shape_proxy_uncertified'
    identity_trusted: bool = True
    common_stock: bool = True
    source: str = 'alpaca'
    feed: str = 'sip'
    adjustment: str = 'split'
    joint_price_volume_adjustment: bool = True
    historical_certified: bool = False

    def refusal(self):
        if not self.identity_trusted or not self.common_stock:
            return 'proxy_identity_untrusted'
        if (self.scope, self.source, self.feed, self.adjustment) != (
            'historical_shape_proxy_uncertified', 'alpaca', 'sip', 'split'
        ) or not self.joint_price_volume_adjustment or self.historical_certified:
            return 'proxy_domain_mismatch'
        return None

    def model_dump(self):
        return asdict(self)


def study():
    value = yaml.safe_load(CONFIG.read_text(encoding='utf-8'))
    if value['selector_version'] != VERSION or value['scope'] != 'exploratory_proxy_only_not_certified_historical_execution':
        raise ValueError('Local Q2 v1.2 proxy contract changed')
    return value


def receipt(cfg):
    with ResearchInfrastructure(ROOT) as api:
        snapshot = api.fingerprint
    home, identity = installation(ROOT)
    paths = [CONFIG, ROOT / 'config/high_beta_channel_v1_2.yaml',
             ROOT / 'config/quant_research_v1.yaml', ROOT / 'config/research.yaml',
             ROOT / 'src/radar/research/high_beta/channel.py',
             ROOT / 'src/radar/research/parallel_channel.py',
             ROOT / 'src/radar/research/historical_quant.py',
             ROOT / 'src/radar/research/quant_lean.py',
             ROOT / 'src/radar/lean/algorithm_fixed_horizon.py']
    result = {'version': cfg['version'], 'created_at': datetime.now(timezone.utc).isoformat(),
              'source_files': {str(p.relative_to(ROOT)).replace('\\', '/'): digest(p) for p in paths},
              'shape_snapshot': snapshot, 'engine_identity': identity,
              'selector_config_hash': fingerprint(asdict(settings(ROOT))),
              'windows': cfg['intervals'], 'scope': cfg['scope']}
    OUTPUT.mkdir(parents=True, exist_ok=True)
    target = OUTPUT / 'receipt.json'
    if target.exists():
        old = json.loads(target.read_text(encoding='utf-8'))
        if {k: v for k, v in old.items() if k != 'created_at'} != {k: v for k, v in result.items() if k != 'created_at'}:
            raise ValueError('Q2 v1.2 proxy study receipt drift')
        return old
    target.write_text(json.dumps(result, indent=2, allow_nan=False), encoding='utf-8')
    return result


def check_receipt(saved):
    for name, expected in saved['source_files'].items():
        if digest(ROOT / name) != expected:
            raise ValueError('Frozen local proxy source changed: ' + name)
    if installation(ROOT)[1] != saved['engine_identity']:
        raise ValueError('Native LEAN build changed')


def _benchmarks(first, end):
    with duckdb.connect(str(ROOT / 'data/market.duckdb'), read_only=True) as db:
        refs = db.execute("""select symbol,date,close,provider,feed,adjustment from daily_bars
            where symbol in ('SPY','QQQ') and date between ? and ? order by symbol,date""",
                          [first, end]).df()
    result = {symbol: group.drop(columns='symbol').copy() for symbol, group in refs.groupby('symbol')}
    for symbol in ('SPY', 'QQQ'):
        if symbol not in result or not (result[symbol].provider.eq('alpaca') &
              result[symbol].feed.eq('sip') & result[symbol].adjustment.eq('split')).all():
            raise ValueError('Missing homogeneous Alpaca SIP benchmark: ' + symbol)
    return result


def scan(split, window, saved):
    start, end, _ = window
    sessions = calendar().sessions_in_range(start, end)
    first = calendar().sessions[calendar().sessions.get_indexer([pd.Timestamp(start)])[0] - 430]
    refs = _benchmarks(str(first.date()), end)
    folder = OUTPUT / split
    folder.mkdir(parents=True, exist_ok=True)
    with ResearchInfrastructure(ROOT) as api:
        if api.fingerprint != saved['shape_snapshot']:
            raise ValueError('Frozen Shape snapshot changed')
        c = api.core.connection
        idx = c.execute("""select * from universe_window_index
            where decision_date between ? and ? and length=126 and supported_membership
              and source=? and basis='split'
            qualify row_number() over(partition by security_id,decision_date
              order by priority,series_id)=1
            order by decision_date,security_id""", [start, end, SOURCE]).df()
        if idx.empty:
            raise ValueError('No supported historical Alpaca proxy windows')
        c.register('proxy_series', pd.DataFrame({'series_id': sorted(idx.series_id.unique())}))
        bars = c.execute("""select p.* from shape_price p join proxy_series s using(series_id)
            where p.date between ? and ? order by p.series_id,p.date""",
                         [first.date(), pd.Timestamp(end).date()]).df()
    groups = {}
    for series, group in bars.groupby('series_id', sort=False):
        frame = group.reset_index(drop=True)
        amount = (frame.close * frame.volume).to_numpy(dtype=float)
        groups[series] = (frame, frame.date.to_numpy(dtype='datetime64[ns]'),
                          np.r_[0., np.cumsum(amount)])
    cfg = settings(ROOT)
    evidence = ProxyEvidence()
    signals = []
    audits = []
    exclusions = Counter()
    for day in sessions:
        day_text = str(day.date())
        eligible = idx.loc[idx.decision_date.eq(day)]
        qualified = []
        daily = Counter()
        spy = refs['SPY'].loc[refs['SPY'].date.le(day)]
        qqq = refs['QQQ'].loc[refs['QQQ'].date.le(day)]
        for row in eligible.itertuples(index=False):
            frame, dates, cumulative = groups[row.series_id]
            stop = int(np.searchsorted(dates, np.datetime64(day), side='right'))
            if stop < 20 or dates[stop - 1] != np.datetime64(day):
                daily['missing_decision_or_adv'] += 1
                continue
            amount = (cumulative[stop] - cumulative[stop - 20]) / 20
            if not np.isfinite(amount) or amount < cfg.adv20_minimum:
                daily['liquidity_below_minimum'] += 1
                continue
            try:
                prefix = long_prefix(frame.iloc[max(0, stop - 430):stop], day_text)
            except ValueError as error:
                daily[str(error)] += 1
                continue
            # This assumption belongs only to the proxy adapter. The original
            # historical-certified MarketEvidence and selector stay untouched.
            result = analyze(prefix, day_text, spy, qqq, evidence, cfg)
            if result['market_qualified']:
                daily['market_qualified'] += 1
            if result['structure_qualified']:
                daily['structure_qualified'] += 1
            if result['watch']:
                daily['watch'] += 1
            if result['qualified']:
                daily['qualified'] += 1
                qualified.append(candidate(result, security_id=row.security_id,
                   symbol=row.historical_ticker,
                   provenance={'series_id': row.series_id, 'source': row.source,
                               'basis': row.basis, 'domain': evidence.scope}))
            else:
                daily[result['reason_codes'][0]] += 1
        chosen = rank(qualified)[:10]
        for item in chosen:
            signals.append({'method': 'q2_parallel_channel', 'version': VERSION,
                            'decision_date': day_text, 'security_id': item.security_id,
                            'symbol': item.symbol, 'score': item.score, 'rank': item.rank,
                            'selected': True, 'provenance': item.provenance})
        daily['selected'] = len(chosen)
        daily['eligible'] = len(eligible)
        exclusions.update({k: v for k, v in daily.items() if k not in
                          {'eligible', 'market_qualified', 'structure_qualified', 'watch', 'qualified', 'selected'}})
        audits.append({'date': day_text, **dict(daily)})
        print(f'{split} {day_text}: eligible={len(eligible)} market={daily["market_qualified"]} '
              f'structure={daily["structure_qualified"]} qualified={daily["qualified"]} selected={len(chosen)}', flush=True)
    report = {'version': study()['version'], 'split': split, 'window': window,
              'scope': evidence.scope, 'shape_snapshot': saved['shape_snapshot'],
              'selector_config_hash': saved['selector_config_hash'],
              'days': len(audits), 'eligible_security_days': sum(r['eligible'] for r in audits),
              'market_qualified': sum(r.get('market_qualified', 0) for r in audits),
              'structure_qualified': sum(r.get('structure_qualified', 0) for r in audits),
              'qualified': sum(r.get('qualified', 0) for r in audits),
              'selected_signals': len(signals), 'exclusions': dict(exclusions),
              'sessions': audits, 'limitations': study()['limitations']}
    (folder / 'signals.jsonl').write_text(''.join(json.dumps(r, sort_keys=True,
        separators=(',', ':'), allow_nan=False) + '\n' for r in signals), encoding='utf-8')
    (folder / 'audit.json').write_text(json.dumps(report, indent=2, allow_nan=False), encoding='utf-8')
    return report


def execute(split, window, saved):
    folder = OUTPUT / split
    rows = [json.loads(line) for line in (folder / 'signals.jsonl').read_text(encoding='utf-8').splitlines()]
    gate, sessions, signals, prices, mapping = execution_inputs(ROOT, rows, window)
    (folder / 'execution-gate.json').write_text(json.dumps(gate, indent=2), encoding='utf-8')
    if gate['status'] == 'BLOCKED':
        return {'status': 'BLOCKED', 'split': split, 'gate': gate}
    cfg = yaml.safe_load((ROOT / 'config/quant_research_v1.yaml').read_text(encoding='utf-8'))
    execution = execution_config(cfg)
    home, identity = installation(ROOT)
    run_id = str(uuid4())
    output = folder / ('lean-' + run_id)
    metadata = {'run_id': run_id, 'strategy_id': 'q2_parallel_channel',
        'strategy_version': VERSION, 'strategy_name': 'Q2 v1.2 local proxy (exploratory)',
        'engine': 'lean', 'engine_identity': identity,
        'engine_code_hash': digest(ROOT / 'src/radar/lean/algorithm_fixed_horizon.py'),
        'universe_mode': 'shape_research_v1_proxy', 'quality_tier': 'uncertified_historical_proxy',
        'window': window, 'split': split, 'start_date': window[0], 'end_date': window[1],
        'evaluation_end': window[2], 'initial_capital': cfg['initial_capital'],
        'git_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT,
            text=True).strip(),
        'signal_source': 'frozen Shape Research Q2 v1.2 local proxy',
        'data_snapshot': saved['shape_snapshot'], 'source_watermark': window[2],
        'plugin_interface_version': 'frozen-signals-v1',
        'strategy_path': 'radar.research.high_beta.channel',
        'strategy_code_hash': saved['source_files']['src/radar/research/high_beta/channel.py'],
        'feature_version': VERSION, 'config': asdict(settings(ROOT)),
        'config_hash': saved['selector_config_hash'],
        'fee_profile': load_fee_config(ROOT / 'config/research.yaml').profile,
        'slippage_bps': cfg['slippage_bps'], 'execution_policy': execution_display(execution),
        'backtest_config_hash': fingerprint(execution),
        'research_config_hash': fingerprint(study()), 'resolved_execution': execution,
        'selector_freeze': fingerprint(saved), 'execution_preflight': gate,
        'private_security_mapping': mapping, 'price_proxy_limitations': study()['limitations']}
    manifest = prepare_bundle(home, output, metadata, list(sessions), signals, prices,
                              execution, load_fee_config(ROOT / 'config/research.yaml'), max_positions=10)
    raw = invoke(ROOT, output, manifest, run_id, lambda _: None, lambda: False,
                 expected_identity=identity)
    result, metrics = normalize(output, raw, identity)
    for collection in ('trades', 'orders', 'open_positions'):
        for item in result[collection]:
            if item['symbol'] in mapping:
                item.update(mapping[item['symbol']])
    for point in result['equity']:
        for item in point['positions']:
            if item['symbol'] in mapping:
                item.update(mapping[item['symbol']])
    if any(t['holding_sessions'] != 10 or t['exit_reason'] != 'fixed_horizon_close'
           for t in result['trades']) or result['open_positions']:
        raise ValueError('Native fixed-horizon execution did not settle correctly')
    check_receipt(saved)
    publish_result(ROOT, result, metrics, metadata)
    summary = {'status': 'PASS_EXPLORATORY_PROXY_ONLY', 'split': split, 'run_id': run_id,
               'strategy_version': VERSION, 'selected_signals': len(rows),
               'metrics': metrics, 'engine_identity': identity,
               'signal_snapshot': digest(folder / 'signals.jsonl'),
               'native_result_sha256': digest(raw), 'path': str(output),
               'limitations': study()['limitations']}
    (folder / 'result-summary.json').write_text(json.dumps(summary, indent=2,
        allow_nan=False), encoding='utf-8')
    return summary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--split', choices=('train', 'validation', 'all'), default='all')
    parser.add_argument('--scan-only', action='store_true')
    parser.add_argument('--execute-only', action='store_true')
    args = parser.parse_args()
    if args.scan_only and args.execute_only:
        parser.error('choose scan-only or execute-only')
    cfg = study()
    saved = receipt(cfg)
    check_receipt(saved)
    for split, window in cfg['intervals'].items():
        if args.split not in ('all', split):
            continue
        for day in window:
            require_session(day)
        if not args.execute_only:
            scan(split, window, saved)
        if not args.scan_only:
            result = execute(split, window, saved)
            print(json.dumps(result, indent=2, allow_nan=False), flush=True)


if __name__ == '__main__':
    main()

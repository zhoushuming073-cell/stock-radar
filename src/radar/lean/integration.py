"""The worker bridge. Generates all signals before invoking the execution engine."""
import json

from radar.backtest.runner import load_spy_ma200_guard
from radar.lean.export import freeze_signals, prepare_bundle, load_prices
from radar.lean.result_adapter import normalize
from radar.lean.runtime import installation, invoke, digest


def execute(root, store, run_id, metadata, frame, sessions, registration, fees):
    from radar.backtest.engine import BacktestCancelled

    def check_cancelled():
        if store.get_run(run_id)['cancel_requested']:
            raise BacktestCancelled('LEAN input preparation cancelled')

    check_cancelled()
    home, identity = installation(root)
    if identity != metadata['engine_identity']:
        raise ValueError('LEAN installation changed after queuing')
    execution = metadata['resolved_config']['values']['execution']
    if execution['execution_timing'] != 'next_open':
        raise ValueError('LEAN requires next-session open execution')
    if metadata.get('universe_mode') == 'point_in_time':
        # Fail rather than invent corporate-action settlements in this first bridge.
        raise ValueError('LEAN PIT terminal/corporate-action support is not yet validated; use Current Snapshot')
    covered = [d for d in sessions if metadata['window'][0] <= str(d.date()) <= metadata['window'][2]]
    guard = (load_spy_ma200_guard(root / 'data/phase2-research.duckdb', covered[-1])
             if execution['market_guard']['mode'] == 'spy_ma200' else None)
    signals, allowed = freeze_signals(frame, covered, metadata, registration.plugin, store, execution, guard)
    prices = load_prices(root / 'data/phase2-research.duckdb', metadata['window'][0],
                         metadata['window'][2], [s['symbol'] for s in signals])
    check_cancelled()
    output = root / 'data/strategy-lab/lean' / run_id
    manifest = prepare_bundle(home, output, metadata, covered, signals, prices, execution, fees, allowed,
                              metadata['lean_max_positions'])
    bundle = json.loads(manifest.read_text(encoding='utf-8'))
    if digest(root / 'data/phase2-research.duckdb') != metadata['data_snapshot']:
        raise ValueError('Research database changed while freezing LEAN inputs')
    check_cancelled()
    manifest_hash = digest(manifest)
    store.bind_execution_artifacts(run_id, {
        'signal_snapshot': bundle['signal_snapshot'], 'signal_source': metadata.get('source_scanner_run_id') or 'Stock Radar historical daily selection',
        'execution_data_snapshot': bundle['data_snapshot'], 'lean_manifest': str(manifest),
        'lean_manifest_sha256': manifest_hash})
    raw = invoke(root, output, manifest, run_id, lambda s: store.append_progress(run_id, s),
                 lambda: store.get_run(run_id)['cancel_requested'], identity, manifest_hash)
    result, metrics = normalize(output, raw, identity)
    store.finish_run(run_id, result, metrics)
    return metrics

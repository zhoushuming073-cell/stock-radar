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
    if metadata.get('quality_tier') not in {None,'vendor-grade','research-grade'}:
        raise ValueError('unknown PIT quality tier; no fallback')
    research_tier=metadata.get('quality_tier')=='research-grade'
    if research_tier and metadata.get('universe_mode')!='point_in_time':
        raise ValueError('Research-Grade PIT requires point_in_time inputs; no Current Snapshot fallback')
    if execution['execution_timing'] != 'next_open':
        raise ValueError('LEAN requires next-session open execution')
    if metadata.get('universe_mode') == 'point_in_time':
        from radar.pit.run import load_dependency, require_ready
        if not metadata.get('pit_dependency'):
            raise ValueError('LEAN PIT run requires a frozen dependency manifest')
        closure = load_dependency(metadata['pit_dependency'])
        if research_tier:
            from radar.pit.research import load_research_acceptance, require_research_ready
            research_audit,research_rules=load_research_acceptance(metadata.get('pit_research_audit'),metadata.get('pit_research_rules'))
            metadata['run_pit_readiness']=require_research_ready(closure,research_audit,research_rules)
        else:
            require_ready(closure)
    covered = [d for d in sessions if metadata['window'][0] <= str(d.date()) <= metadata['window'][2]]
    guard_database=root/'data/phase2-research.duckdb'
    if research_tier:
        from pathlib import Path
        sidecars=[Path(v['path']) for v in closure['files'].values() if Path(v['path']).name=='security-master-feature-store.json']
        if len(sidecars)!=1: raise ValueError('research guard requires frozen raw PIT feature store')
        guard_database=Path(json.loads(sidecars[0].read_text(encoding='utf-8'))['database'])
    guard = (load_spy_ma200_guard(guard_database, covered[-1])
             if execution['market_guard']['mode'] == 'spy_ma200' else None)
    research_mode = metadata.get('universe_mode') == 'research_infrastructure_v1'
    if research_mode:
        from radar.lab.research_backend import ResearchHistory
        with ResearchHistory(root) as history_host:
            if history_host.fingerprint != metadata['research_backend']['semantic_hash']:
                raise ValueError('Research Infrastructure v1 history binding changed')
            signals, allowed = freeze_signals(frame, covered, metadata, registration.plugin,
                                              store, execution, guard, history=history_host.history)
    else:
        signals, allowed = freeze_signals(frame, covered, metadata, registration.plugin, store, execution, guard)
    pit_dataset = None
    if metadata.get('universe_mode') == 'point_in_time':
        from radar.pit.execution import execution_inputs
        from radar.pit.builder import digest as semantic_digest
        # Re-evaluation must match the signal snapshot captured at queue time.
        expected = [{k: v for k, v in s.items() if k != 'security_id'} for s in closure['signals']]
        if semantic_digest(signals) != semantic_digest(expected):
            raise ValueError('queued PIT signals changed')
        signals, prices, pit_dataset = execution_inputs(closure,quality_tier='research-grade',
            research_audit=research_audit,research_rules=research_rules) if research_tier else execution_inputs(closure)
    elif research_mode:
        from radar.lab.research_backend import load_execution_prices
        prices = load_execution_prices(root, frame, signals, metadata['window'][0], metadata['window'][2])
    else:
        prices = load_prices(root / 'data/phase2-research.duckdb', metadata['window'][0],
                             metadata['window'][2], [s['symbol'] for s in signals])
    check_cancelled()
    output = root / 'data/strategy-lab/lean' / run_id
    manifest = prepare_bundle(home, output, metadata, covered, signals, prices, execution, fees, allowed,
                              metadata['lean_max_positions'], pit_dataset=pit_dataset)
    bundle = json.loads(manifest.read_text(encoding='utf-8'))
    source_database=root/'data/phase2-research.duckdb'
    if research_mode:
        from radar.lab.research_backend import ResearchHistory
        with ResearchHistory(root) as history_host:
            source_database = history_host.core_path
    if research_tier:
        source_reference=metadata.get('research_source_database') or {}
        if not source_reference.get('path') or not source_reference.get('sha256'):
            raise ValueError('research raw source reference unavailable; no fallback')
        source_database=Path(source_reference['path'])
        if (source_reference['sha256']!=metadata['data_snapshot'] or
            not any(v['path']==str(source_database.resolve()) and v['sha256']==source_reference['sha256']
                    for v in closure['files'].values())):
            raise ValueError('research raw source does not bind execution closure')
    if digest(source_database) != metadata['data_snapshot']:
        raise ValueError('Research database changed while freezing LEAN inputs')
    check_cancelled()
    manifest_hash = digest(manifest)
    store.bind_execution_artifacts(run_id, {
        'signal_snapshot': bundle['signal_snapshot'], 'signal_source': metadata.get('source_scanner_run_id') or 'Stock Radar historical daily selection',
        'execution_data_snapshot': bundle['data_snapshot'], 'lean_manifest': str(manifest),
        'lean_manifest_sha256': manifest_hash,
        **({'pit_execution_dataset': bundle['pit_dataset']} if pit_dataset else {})})
    raw = invoke(root, output, manifest, run_id, lambda s: store.append_progress(run_id, s),
                 lambda: store.get_run(run_id)['cancel_requested'], identity, manifest_hash)
    if pit_dataset:
        load_dependency(metadata['pit_dependency'])
        if research_tier:
            audit_after,rules_after=load_research_acceptance(metadata['pit_research_audit'],metadata['pit_research_rules'])
            require_research_ready(closure,audit_after,rules_after)
    result, metrics = normalize(output, raw, identity)
    store.finish_run(run_id, result, metrics)
    return metrics

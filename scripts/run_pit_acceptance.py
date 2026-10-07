"""Freeze the existing Validation contract, run both Scanners, and enforce native gates.

Artifacts and Run IDs are resumable. Blocked PIT attempts stay visible in Run
History; a Current result never substitutes for a PIT result.
"""
from pathlib import Path
import json
import time

from radar.lab.manager import RunManager
from radar.pit.features import file_hash
from radar.pit.run import load_dependency
from radar.pit.resolution import ResolutionQueue, work


def main():
    root=Path.cwd();out=root/'data/pit/final-acceptance';out.mkdir(parents=True,exist_ok=True)
    plan=root/'config/pit_final_run_plan.json';spec=json.loads(plan.read_text(encoding='utf-8'))
    receipt=out/'formal-run-receipt.json'
    state=json.loads(receipt.read_text(encoding='utf-8')) if receipt.exists() else {'plan_sha256':file_hash(plan)}
    if state['plan_sha256']!=file_hash(plan):raise ValueError('frozen acceptance plan changed')
    manager=RunManager(root)
    def save():receipt.write_text(json.dumps(state,indent=2),encoding='utf-8')
    if 'scanners' not in state:
        ids=manager.queue_scanner_requests([{'strategy_id':spec['strategy_ref'],'split':spec['split'],
            'universe_mode':mode} for mode in ('current_snapshot','point_in_time')])
        state['scanners']=dict(zip(('current_snapshot','point_in_time'),ids));save()
    for mode,run_id in state['scanners'].items():
        record=manager.store.get_scanner_run(run_id)
        if record['status']=='failed' and 'worker stopped' in (record.get('error_text') or ''):
            state.setdefault('superseded_scanners',[]).append({'run_id':run_id,'mode':mode,'error':record.get('error_text')})
            run_id=manager.queue_scanner(spec['strategy_ref'],split=spec['split'],universe_mode=mode)
            state['scanners'][mode]=run_id;save()
        print('Scanner '+mode+' '+run_id,flush=True)
        while manager.store.get_scanner_run(run_id)['status'] in {'queued','running','cancel_requested'}:
            manager.dispatch_queued()
            time.sleep(2)
        if manager.store.get_scanner_run(run_id)['status']!='completed':
            raise ValueError('Scanner did not complete: '+run_id)
    if 'backtests' not in state:
        requests=[{'strategy_ids':[spec['strategy_ref']],'split':spec['split'],'engine':'lean',
            'universe_mode':mode,'source_scanner_run_id':state['scanners'][mode]} for mode in ('current_snapshot','point_in_time')]
        ids=manager.queue_run_requests(requests)
        state['backtests']=dict(zip(('current_snapshot','point_in_time'),ids));save()
    pit=manager.store.get_run(state['backtests']['point_in_time'])
    closure=load_dependency(pit['metadata']['pit_dependency'])
    queue=ResolutionQueue(out/'resolution.sqlite3');queue.seed(closure)
    state['dependency']=pit['metadata']['pit_dependency'];state['run_readiness']=pit['metadata']['run_pit_readiness'];save()
    for mode,run_id in state['backtests'].items():
        record=manager.store.get_run(run_id)
        print('LEAN attempt '+mode+' '+run_id,flush=True)
        while manager.store.get_run(run_id)['status'] in {'queued','running','cancel_requested'}:
            manager.dispatch_queued()
            time.sleep(2)
        record=manager.store.get_run(run_id)
        state[mode+'_backtest']={'run_id':run_id,'status':record['status'],'metrics':record.get('metrics'),
                                'error':record.get('error_text'),'metadata':record['metadata']};save()
        if mode=='current_snapshot' and record['status']!='completed':
            raise ValueError('Current native comparison did not complete: '+str(record.get('error_text')))
    # Batch local evidence assessment across the actual P0 population. Network
    # fetching is a separate bounded queue command; unknown identities stay blocked.
    outcomes=work(root,queue,limit=1000)
    state['resolution_queue']=queue.summary();state['resolution_batch_count']=len(outcomes);save()
    (out/'resolution-local-outcomes.json').write_text(json.dumps(outcomes,indent=2),encoding='utf-8')
    selected={mode:{(r['signal_date'],r['symbol']) for r in manager.store.get_scanner_candidates(run_id,limit=10000000)
                   if r['selected']} for mode,run_id in state['scanners'].items()}
    current,pit=selected['current_snapshot'],selected['point_in_time']
    comparison={'plan_sha256':state['plan_sha256'],'dependency_sha256':closure['dependency_sha256'],
        'current_selected':len(current),'pit_selected':len(pit),'intersection':len(current&pit),
        'current_only':sorted(current-pit),'pit_only':sorted(pit-current),
        'scanner_metrics':{mode:manager.store.get_scanner_run(run_id)['metrics'] for mode,run_id in state['scanners'].items()},
        'current_portfolio':state['current_snapshot_backtest'],'pit_portfolio':state['point_in_time_backtest'],
        'portfolio_delta':None if state['point_in_time_backtest']['status']!='completed' else 'compute from normalized results',
        'interpretation':'membership, product classification, price coverage, causal warm-up and population-ranking effects are mixed; not a causal survivorship-bias percentage',
        'research_validity':'retrospective research validation, not Fresh OOS'}
    (out/'comparison.json').write_text(json.dumps(comparison,indent=2),encoding='utf-8')
    print(json.dumps({'scanners':state['scanners'],'backtests':state['backtests'],'queue':state['resolution_queue'],
                      'readiness':{k:v for k,v in state['run_readiness'].items() if k!='reasons_by_gate'}},indent=2),flush=True)


if __name__=='__main__':main()

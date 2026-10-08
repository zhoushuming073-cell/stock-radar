"""Offline preparation/import. Production Stock Radar never imports this module."""
from __future__ import annotations

import argparse
import ast
import base64
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys
import zlib

import yaml

HOME = Path(__file__).resolve().parent
ROOT = HOME.parent
sys.path.insert(0, str(HOME / 'cloud'))
from protocol import canonical, digest, parse_receipt, CLASSES, historical_join

MAX_FILE_BYTES = 32000  # Conservative KB, not 32 KiB.
MAX_FILES = 24          # Reserve default research.ipynb in QC's 25-file project.
EVIDENCE = 'reports/evidence/pit-research-final-evidence-2026-10-07.json'
PRIORITY = 'reports/evidence/pit-research-final-priority-2026-10-07.json'
INPUT_PATHS = [EVIDENCE, PRIORITY, 'quantconnect-validation/local.py', 'quantconnect-validation/evidence.py',
    'config/pit_research_grade_rules.json',
    'config/pit_research_decision_rules.json', 'config/research.yaml', 'config/lean.yaml',
    'strategies/full_strategy2_v1/strategy.yaml', 'strategies/full_strategy2_v1/manifest.yaml',
    'data/pit/research-grade/core-universe.json', 'data/pit/research-grade/scanner-C.json',
    'data/pit/research-grade/research-run-metadata.json', 'data/pit/research-grade/audit.json',
    'data/pit/research-final/focused-resolutions/candidate-audit.json',
    'data/pit/research-final/identity-safe-bounds/core-rank-stability.json',
    'data/pit/source-breakthrough/reference-coverage.json']
MODULES = {
    'radar.features.base': 'qc_base_features', 'radar.features.elasticity': 'qc_elasticity',
    'radar.features.scoring': 'qc_scoring', 'radar.features.strategy2': 'qc_strategy_features',
    'radar.strategy.context': 'qc_context', 'radar.strategy.base': 'qc_base',
    'radar.strategy.full_strategy2': 'qc_full_strategy2',
    'radar.strategy.adapter': 'qc_adapter', 'radar.strategy.validation': 'qc_future_guard',
    'radar.pit.actions': 'qc_split', 'radar.pit.features': 'qc_causal_features',
    'radar.pit.research': 'qc_core', 'radar.lean.algorithm': 'qc_execution_source',
}
SOURCES = {name: 'src/' + module.replace('.', '/') + '.py' for module, name in MODULES.items()}
SOURCES['qc_plugin'] = 'strategies/full_strategy2_v1/strategy.py'
EXTRACT = {'qc_future_guard': ['_FUTURE_COLUMNS', 'is_future_feature'],
           'qc_core': ['core_membership'], 'qc_split': ['split_adjust'],
           'qc_causal_features': ['causal_identity_features']}
PREAMBLES = {
    'qc_future_guard': '', 'qc_core': 'import numpy as np\nimport pandas as pd\n',
    'qc_split': 'import math\nimport pandas as pd\n',
    'qc_causal_features': 'import pandas as pd\nfrom qc_base_features import compute_base_features\n'
        'from qc_elasticity import compute_elasticity_inputs\n'
        'from qc_scoring import tradability_gate\nfrom qc_strategy_features import compute_strategy2_features\n'}


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def write(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + '\n',
                    encoding='utf-8', newline='\n')


class RelocateImports(ast.NodeTransformer):
    def visit_ImportFrom(self, node):
        if node.level == 1 and node.module == 'base':
            node.module, node.level = 'qc_base_features', 0
        elif node.module in MODULES:
            node.module = MODULES[node.module]
        return node


def snapshot_source(name, text):
    original = ast.parse(text)
    if name in EXTRACT:
        names = EXTRACT[name]
        nodes = [node for node in original.body if getattr(node, 'name', None) in names
                 or isinstance(node, ast.Assign) and any(getattr(t, 'id', None) in names for t in node.targets)]
        if len(nodes) != len(names):
            raise ValueError('Snapshot extraction no longer matches source: ' + name)
        original = ast.Module(body=nodes, type_ignores=[])
    tree = RelocateImports().visit(original)
    result = PREAMBLES.get(name, '') + ast.unparse(ast.fix_missing_locations(tree)) + '\n'
    compile(result, name, 'exec')
    # Only import names are transformed. Formulas, defaults, comparisons and ranking remain original AST.
    return result


def check_quota(files):
    if len(files) > MAX_FILES:
        raise ValueError('Free file-count quota exceeded (default notebook reserved)')
    sizes = {name: len(content.encode('utf-8')) for name, content in files.items()}
    if any(size > MAX_FILE_BYTES for size in sizes.values()):
        raise ValueError('Free file-size quota exceeded')
    for name, text in files.items():
        if name.endswith('.py'):
            compile(text, name, 'exec')
    return {'upload_files': len(files), 'reserved_notebook': 1,
            'total_with_notebook': len(files) + 1, 'max_file_bytes': max(sizes.values()),
            'file_bytes': sizes, 'limits': {'files': 25, 'file_bytes_conservative': MAX_FILE_BYTES}}


def check_signals(signals):
    allowed = {'signal_date', 'available_at', 'symbol', 'historical_ticker', 'security_id', 'rank',
               'strategy_score', 'strategy_id', 'strategy_version', 'reference_close',
               'avg_dollar_volume_20', 'allocation_weight', 'mapping_reference'}
    keys = set()
    for row in signals:
        if set(row) != allowed:
            raise ValueError('Frozen signal fields drift/future data detected')
        stamp = datetime.fromisoformat(row['available_at'])
        if stamp.tzinfo is None or str(stamp.date()) != row['signal_date']:
            raise ValueError('Frozen signal availability invalid')
        key = (row['signal_date'], row['security_id'])
        if key in keys:
            raise ValueError('Duplicate frozen signal')
        keys.add(key)
    return digest(signals)


def prepare():
    evidence, priority = read(ROOT / EVIDENCE), read(ROOT / PRIORITY)
    metadata = read(ROOT / 'data/pit/research-grade/research-run-metadata.json')
    core = read(ROOT / 'data/pit/research-grade/core-universe.json')
    scanner = read(ROOT / 'data/pit/research-grade/scanner-C.json')
    candidate_audit = read(ROOT / 'data/pit/research-final/focused-resolutions/candidate-audit.json')
    rules = read(ROOT / 'config/pit_research_grade_rules.json')
    bounds = read(ROOT / 'data/pit/research-final/identity-safe-bounds/core-rank-stability.json')
    reference = read(ROOT / 'data/pit/source-breakthrough/reference-coverage.json')
    audit = read(ROOT / 'data/pit/research-grade/audit.json')
    closure_path = Path(audit['dependency_reference']['path'])
    if sha(closure_path) != audit['dependency_reference']['sha256']:
        raise ValueError('PIT closure physical hash changed')
    closure = read(closure_path)
    research = yaml.safe_load((ROOT / 'config/research.yaml').read_text(encoding='utf-8'))
    strategy = yaml.safe_load((ROOT / 'strategies/full_strategy2_v1/strategy.yaml').read_text(encoding='utf-8'))
    if strategy != metadata['config']:
        raise ValueError('Frozen Strategy 2 configuration drift')
    if [metadata['start_date'], metadata['end_date'], metadata['evaluation_end']] != rules['window']:
        raise ValueError('Frozen validation window drift')
    source_hashes, snapshots = {}, {}
    for name, source in SOURCES.items():
        path = ROOT / source
        source_hashes[source] = sha(path)
        text = snapshot_source(name, path.read_text(encoding='utf-8'))
        snapshots[name + '.py'] = text
        destination = HOME / 'snapshots' / (name + '.py')
        destination.parent.mkdir(exist_ok=True)
        destination.write_text(text, encoding='utf-8', newline='\n')
    for path, expected in metadata['host_source_hashes'].items():
        if path in source_hashes and source_hashes[path] != expected:
            raise ValueError('Frozen host source changed: ' + path)
    days = [d['date'] for d in core['days']]
    if days != sorted(bounds['remaining_competitors']):
        raise ValueError('Core/unknown calendars differ')
    from radar.pit.sources import effective_day
    obs_dates = {r['sha']: str(effective_day(r['date'].replace('Z', '+00:00')))
                 for r in reference['receipts']['cik']}
    observed = {r['security_id']: [{'cik': o['cik'], 'available_on': obs_dates[o['snapshot']],
                                  'source_snapshot': o['snapshot']} for o in r['dated_issuer_candidates']]
                for r in reference['identity']['rows']}
    # Two earliest independent observations per DISTINCT issuer preserve every
    # historical issuer conflict and availability boundary. Daily repeats are
    # already hash-bound in reference-coverage.json, not duplicated into Cloud.
    for uid, facts in observed.items():
        per_issuer = defaultdict(list)
        for fact in sorted(facts, key=lambda o: (o['available_on'], o['source_snapshot'])):
            records = per_issuer[str(fact['cik']).zfill(10)]
            if len(records) < 2 and not any(o['source_snapshot'] == fact['source_snapshot'] for o in records):
                records.append(fact)
        observed[uid] = [fact for cik in sorted(per_issuer) for fact in per_issuer[cik]]
    identities = {}
    for record in closure['dependencies']:
        uid = record['security_id']
        mappings = []
        for m in record['mappings']:
            name = m.get('security_name', '')
            match = re.search(r'\bClass\s+([A-Za-z0-9]+)\b', name, re.I)
            share_class = ('CLASS-' + match.group(1).upper() if match else
                           'ORDINARY' if 'ordinary' in name.lower() else
                           'COMMON' if 'common' in name.lower() else '')
            mappings.append({'ticker': m['symbol'], 'from': m['valid_from'][:10],
                             'to': m['valid_to'][:10] if m.get('valid_to') else None,
                             'class': share_class, 'source': m['first_source_commit']})
        identities[uid] = {'uid': uid, 'mappings': mappings, 'issuers': observed.get(uid, [])}
    universe_by_day = {d['date']: d['security_ids'] for d in core['days']}
    candidates = defaultdict(list)
    signals = []
    from zoneinfo import ZoneInfo
    for r in scanner['rows']:
        uid, day = r['security_id'], r['signal_date']
        candidates[day].append({'uid': uid, 'rank': r['rank'], 'score': r['strategy_score'],
                                'selected': r['selected'], 'historical_ticker': r['symbol']})
        if not r['selected']:
            continue
        signal = {k: r[k] for k in ['signal_date', 'symbol', 'rank', 'strategy_score', 'security_id']}
        available = datetime.fromisoformat(day).replace(hour=16, tzinfo=ZoneInfo('America/New_York'))
        signal.update({'available_at': available.isoformat(), 'historical_ticker': r['symbol'],
            'strategy_id': metadata['strategy_id'], 'strategy_version': metadata['strategy_version'],
            'reference_close': r['features']['close'], 'avg_dollar_volume_20': r['features']['avg_dollar_volume_20'],
            'allocation_weight': 1., 'mapping_reference': digest(identities[uid]['mappings'])})
        signals.append(signal)
    signals.sort(key=lambda r: (r['signal_date'], r['rank'], r['symbol']))
    signal_hash = check_signals(signals)
    source_snapshots = {name: hashlib.sha256(text.encode()).hexdigest() for name, text in snapshots.items()}
    template_hashes = {p.name: sha(p) for p in sorted((HOME / 'cloud').glob('*.py'))}
    input_hashes = {p: sha(ROOT / p) for p in INPUT_PATHS}
    input_hashes['src/radar/pit/sources.py'] = sha(ROOT / 'src/radar/pit/sources.py')
    input_hashes[str(closure_path.relative_to(ROOT)).replace('\\', '/')] = sha(closure_path)
    ecfg = {k: v for k, v in research['elasticity'].items() if k in {
        'history_window', 'history_min', 'burst_quantile', 'hit_5_weight', 'hit_10_weight'}}
    common = {'core_rules': rules, 'strategy': strategy, 'execution': metadata['resolved_config']['values']['execution'],
              'fees': research['illustrative_costs'], 'max_positions': metadata['lean_max_positions'],
              'feature_start': min(closure['benchmarks'][0]['required_sessions']),
              'feature_config': {'weights': research['elasticity']['weights'], **research['tradability']},
              'elasticity_config': ecfg, 'evaluation_end': metadata['evaluation_end']}
    frozen = {'schema': 1, 'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'original_pit_dependency': closure['dependency_sha256'], 'signal_hash': signal_hash,
        'input_hashes': input_hashes, 'source_hashes': source_hashes, 'snapshot_hashes': source_snapshots,
        'template_hashes': template_hashes, 'common': common, 'identities': identities,
        'local_core': universe_by_day, 'unknown': bounds['remaining_competitors'],
        'candidates': dict(candidates), 'signals': signals,
        'accepted_local_candidate_identities': {r['security_id']: r['identity'] for r in candidate_audit['profiles']['C']
                                                if r['identity']['pass'] is True},
        'sessions': [d for d in closure['calendar'] if days[0] <= d <= metadata['evaluation_end']],
        'latest_local_status': {'uncertainty_range': evidence['effective_core_uncertainty_range'],
             'distinct_competitors': evidence['remaining_distinct_competitors'],
             'candidate_scope': evidence['candidate_scopes']['C'], 'native_execution': evidence['native_execution'],
             'reconciliation': evidence['reconciliation']},
        'signal_status': 'FROZEN_DIAGNOSTIC_C_NOT_FORMAL_PIT_RELEASE',
        'protected_files': evidence['protected_files']}
    write(HOME / 'frozen' / 'inputs.json', frozen)
    runs = [{'id': 'smoke-mapping', 'layer': 'smoke', 'case': 'FB', 'dates': ['2022-06-06', '2022-06-13']},
            {'id': 'smoke-split', 'layer': 'smoke', 'case': 'NVDA', 'dates': ['2024-06-06', '2024-06-12']}]
    for layer in ['layer1', 'layer2']:
        runs += [{'id': layer + '-' + day, 'layer': layer, 'dates': [day]} for day in days]
    runs += [{'id': 'layer3-frozen-C', 'layer': 'layer3', 'dates': [days[0], metadata['evaluation_end']]}]
    write(HOME / 'campaign.json', {'schema': 1, 'frozen_hash': digest(frozen), 'runs': runs,
        'state': 'READY_FOR_QC_FREE_CLOUD_RUN', 'cloud_smoke': 'NOT_RUN',
        'chunk_policy': 'one fixed session for Layer1/2; Layer3 always full continuous portfolio window',
        'membership_gate': 'Local Core vs QC Core; Full/Core Top3 is not a data-quality gate',
        'details_policy': 'hash+25 mismatch IDs per date; samples do not certify full conflict closure'})
    for run_id in ['smoke-mapping', 'smoke-split', runs[2]['id'], 'layer2-' + days[0], 'layer3-frozen-C']:
        stage(run_id, preview=True)
    audit_all_quotas()
    return {'status': 'READY_FOR_QC_FREE_CLOUD_RUN', 'sessions': len(days), 'signals': len(signals),
            'signal_hash': signal_hash, 'runs': len(runs)}


def verify_frozen():
    frozen = read(HOME / 'frozen' / 'inputs.json')
    campaign = read(HOME / 'campaign.json')
    if digest(frozen) != campaign['frozen_hash'] or check_signals(frozen['signals']) != frozen['signal_hash']:
        raise ValueError('Frozen validation inputs changed')
    for collection in ['input_hashes', 'source_hashes']:
        for path, expected in frozen[collection].items():
            if sha(ROOT / path) != expected:
                raise ValueError('Frozen source/input drift: ' + path)
    for name, expected in frozen['template_hashes'].items():
        if sha(HOME / 'cloud' / name) != expected:
            raise ValueError('Cloud transport changed; regenerate a new campaign')
    for name, expected in frozen['snapshot_hashes'].items():
        if sha(HOME / 'snapshots' / name) != expected:
            raise ValueError('Generated strategy/feature snapshot changed')
    return frozen, campaign


def audit_all_quotas():
    """Check all 235 dates, including late dates with more historical evidence."""
    frozen, campaign = verify_frozen()
    rows = []
    for run in campaign['runs']:
        if run['layer'] not in {'layer1', 'layer2'}:
            continue
        inputs = project_input(frozen, run, preview=True)
        size = len(base64.b85encode(zlib.compress(canonical(inputs).encode(), 9)))
        parts = (size + 29999) // 30000
        fixed = 6 if run['layer'] == 'layer1' else 19
        count = fixed + parts
        if count > MAX_FILES:
            raise ValueError('Late-date project exceeds Free quota: ' + run['id'])
        rows.append({'run': run['id'], 'encoded_input_bytes': size, 'parts': parts,
                     'upload_files': count, 'with_default_notebook': count + 1})
    result = {'status': 'PASS', 'checked_date_projects': len(rows),
              'max_with_default_notebook': max(r['with_default_notebook'] for r in rows),
              'max_encoded_input_bytes': max(r['encoded_input_bytes'] for r in rows),
              'max_project_file_bytes': 30010, 'rows': rows}
    write(HOME / 'quota-audit.json', result)
    return result


def smoke_ready():
    path = HOME / 'results' / 'smoke-state.json'
    if not path.exists():
        return False
    state = read(path)
    frozen = read(HOME / 'frozen' / 'inputs.json')
    expected_code = digest({'snapshots': frozen['snapshot_hashes'], 'templates': frozen['template_hashes']})
    return all(state.get(run, {}).get('status') == 'PASS' and
               state[run].get('code_hash') == expected_code and
               state[run].get('origin') == 'quantconnect_cloud_download' and
               state[run].get('backtest_id') and state[run].get('receipt_verified') is True
               for run in ['smoke-mapping', 'smoke-split'])


def project_input(frozen, run, preview):
    inputs = dict(frozen['common'])
    inputs['prerequisite_smoke_verified'] = smoke_ready()
    if run['layer'] == 'smoke':
        return {'case': run['case'], 'dates': run['dates']}
    if not preview and not inputs['prerequisite_smoke_verified']:
        raise ValueError('BOTH real Cloud smoke PASS receipts required before Layer1/2/3 staging')
    if run['layer'] in {'layer3', 'layer3-detail'}:
        binding_path = HOME / 'results' / 'accepted-bindings.json'
        bindings = read(binding_path) if binding_path.exists() else {}
        needed = {r['security_id'] for r in frozen['signals']}
        valid = set(bindings) == needed and all(
            b.get('qc_sid') and b.get('evidence_sha256') and b.get('verified_by_rule') is True
            and b.get('available_on', '9999-12-31') <= min(r['signal_date'] for r in frozen['signals'] if r['security_id'] == uid)
            for uid, b in bindings.items())
        valid = valid and len({b['qc_sid'] for b in bindings.values()}) == len(bindings)
        if valid:
            spec = importlib.util.spec_from_file_location('srqc_official_evidence', HOME / 'evidence.py')
            evidence_rules = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(evidence_rules)
            for uid, binding in bindings.items():
                case_path = Path(binding.get('evidence_path', ''))
                if not case_path.is_file() or sha(case_path) != binding['evidence_sha256']:
                    valid = False
                    break
                if binding.get('method') == 'existing_local_qc_agreement':
                    first = min(r['signal_date'] for r in frozen['signals'] if r['security_id'] == uid)
                    witness = binding.get('qc_identity', {})
                    receipt = read(case_path)
                    references = [ref for row in receipt.get('records', [])
                                  for ref in row.get('execution_identity_references', [])]
                    dictionary = binding_receipt_dictionary(receipt, frozen)
                    q, _ = historical_join(frozen['identities'][uid], [witness], first)
                    if (uid not in frozen['accepted_local_candidate_identities'] or q is None or
                            q['sid'] != binding['qc_sid'] or receipt.get('origin') != 'quantconnect_cloud_download' or
                            receipt.get('receipt_verified') is not True or witness not in references or
                            dictionary is None or dictionary.get(witness.get('index'), {}).get('uid') != uid):
                        valid = False
                        break
                    continue
                case = read(case_path)
                result = evidence_rules.validate_case(case)
                if (case['local_uid'] != uid or result['evidence_status'] != 'PASS' or
                        not result['asof_selection_usable'] or result['qc_sid'] != binding['qc_sid']):
                    valid = False
                    break
        if not preview and not valid:
            raise ValueError('Layer3 identity bindings pending; no ticker-only/current fallback')
        inputs.update({'identity_bindings_verified': valid, 'bindings': bindings,
            'signals': frozen['signals'], 'signal_hash': frozen['signal_hash'],
            'bundle': {'sessions': frozen['sessions'], 'execution': inputs['execution'], 'fees': inputs['fees'],
                'max_positions': inputs['max_positions'], 'market_allowed': {d: True for d in frozen['sessions']},
                'run_metadata': {'universe_mode': 'point_in_time'}, 'pace_ms': 0}})
        return inputs
    day = run['dates'][0]
    uids = sorted(set(frozen['local_core'][day]) | set(frozen['unknown'][day]) |
                  {r['uid'] for r in frozen['candidates'].get(day, [])})
    indices = {uid: n for n, uid in enumerate(uids)}
    local = {'identities': {str(indices[uid]): json.loads(json.dumps(frozen['identities'][uid])) for uid in uids},
             'core': [str(indices[uid]) for uid in frozen['local_core'][day]],
             'unknown': [str(indices[uid]) for uid in frozen['unknown'][day]],
             'candidates': [{'index': str(indices[r['uid']]), **r} for r in
                            sorted(frozen['candidates'].get(day, []), key=lambda r: (r['rank'], r['historical_ticker']))]}
    first_dates = {}
    for signal in frozen['signals']:
        first_dates.setdefault(signal['security_id'], signal['signal_date'])
    local['execution_identity_requests'] = [str(indices[uid]) for uid in uids
                                           if first_dates.get(uid) == day and uid in frozen['accepted_local_candidate_identities']]
    # Only dated issuer facts available by this session enter historical bridging.
    for identity in local['identities'].values():
        identity['issuers'] = [o for o in identity['issuers'] if o['available_on'] <= day]
        identity['mappings'] = [m for m in identity['mappings'] if m['from'] <= day]
    inputs['local'] = {day: local}
    return inputs


def stage(run_id, *, preview=False):
    frozen, campaign = verify_frozen()
    matches = [r for r in campaign['runs'] if r['id'] == run_id]
    detail = re.fullmatch(r'layer1-detail-(\d{4}-\d{2}-\d{2})-b(\d{2})', run_id)
    if not matches and detail and detail[1] in frozen['local_core'] and 0 <= int(detail[2]) < 32:
        matches = [{'id': run_id, 'layer': 'layer1-detail', 'dates': [detail[1]], 'bucket': int(detail[2])}]
    execution_detail = re.fullmatch(r'layer3-detail-b(\d{3})', run_id)
    if not matches and execution_detail and 0 <= int(execution_detail[1]) < 128:
        matches = [{'id': run_id, 'layer': 'layer3-detail', 'dates': [frozen['sessions'][0], frozen['common']['evaluation_end']],
                    'bucket': int(execution_detail[1])}]
    if len(matches) != 1:
        raise ValueError('Unknown predetermined run')
    run = dict(matches[0])
    inputs = project_input(frozen, run, preview)
    run['input_hash'] = digest(inputs)
    run['code_hash'] = digest({'snapshots': frozen['snapshot_hashes'], 'templates': frozen['template_hashes']})
    files = {}
    cloud = lambda name: (HOME / 'cloud' / name).read_text(encoding='utf-8')
    if run['layer'] == 'smoke':
        transport = cloud('data_adapter.py').replace('from qc_protocol import normalize_cik, normalize_class\n', '')
        files['main.py'] = cloud('protocol.py') + '\n' + transport + '\nRUN = ' + repr(run) + '\n' + cloud('smoke.py')
    else:
        files['qc_protocol.py'] = cloud('protocol.py')
        if run['layer'] in {'layer3', 'layer3-detail'}:
            files['main.py'] = cloud('execution_adapter.py')
            files['qc_execution_source.py'] = (HOME / 'snapshots' / 'qc_execution_source.py').read_text(encoding='utf-8')
        else:
            for src, target in [('main_validation.py', 'main.py'), ('data_adapter.py', 'qc_data_adapter.py'),
                                ('membership.py', 'qc_membership.py')]:
                files[target] = cloud(src)
            names = ['qc_core.py'] if run['layer'] in {'layer1', 'layer1-detail'} else [n for n in frozen['snapshot_hashes'] if n != 'qc_execution_source.py']
            for name in names:
                files[name] = (HOME / 'snapshots' / name).read_text(encoding='utf-8')
            if run['layer'] == 'layer2':
                files['qc_strategy_adapter.py'] = cloud('strategy_adapter.py')
        encoded = base64.b85encode(zlib.compress(canonical(inputs).encode(), 9)).decode()
        chunks = [encoded[n:n + 30000] for n in range(0, len(encoded), 30000)]
        imports = []
        for n, chunk in enumerate(chunks):
            name = 'qc_part_' + str(n).zfill(2)
            files[name + '.py'] = 'DATA = ' + repr(chunk) + '\n'
            imports.append('from ' + name + ' import DATA as PART_' + str(n))
        files['qc_input.py'] = '\n'.join(imports) + '\nimport base64, zlib, json\nfrom qc_protocol import digest\n' + \
            'RUN = ' + repr(run) + '\nINPUT = json.loads(zlib.decompress(base64.b85decode(' + \
            ' + '.join('PART_' + str(n) for n in range(len(chunks))) + ')))\n' + \
            "if digest(INPUT) != RUN['input_hash']:\n    raise ValueError('Frozen project input hash mismatch')\n"
    quota = check_quota(files)
    destination = HOME / ('projects' if run['layer'] == 'smoke' else 'work') / run_id
    destination.mkdir(parents=True, exist_ok=True)
    # Retire only our unchanged old data chunks after deterministic compression.
    previous_manifest = destination / 'upload-manifest.json'
    if previous_manifest.exists():
        previous = read(previous_manifest)
        for obsolete in set(previous['upload']) - set(files):
            target = destination / obsolete
            if not re.fullmatch(r'qc_part_\d{2}\.py', obsolete) or target.resolve().parent != destination.resolve():
                raise ValueError('Unexpected obsolete stage file')
            if target.exists():
                if sha(target) != previous['upload'][obsolete]:
                    raise ValueError('Old generated chunk has local changes')
                target.unlink()
    # Never clear a directory recursively; refuse unexpected files instead.
    expected_names = set(files) | {'upload-manifest.json'}
    if any(p.name not in expected_names for p in destination.iterdir()):
        raise ValueError('Stage contains unexpected files; choose a fresh workspace')
    for name, text in files.items():
        (destination / name).write_text(text, encoding='utf-8', newline='\n')
    manifest = {'run': run, 'input_hash': run['input_hash'], 'cloud_executed': False,
        'preview_only': preview and run['layer'] != 'smoke', 'quota': quota,
        'upload': {n: hashlib.sha256(t.encode()).hexdigest() for n, t in files.items()},
        'local_uid_dictionary': inputs.get('local', {}).get(run['dates'][0], {}).get('identities', {}),
        'signal_hash': frozen['signal_hash'] if run['layer'] in {'layer3', 'layer3-detail'} else None,
        'smoke_verified': inputs.get('prerequisite_smoke_verified', False)}
    write(destination / 'upload-manifest.json', manifest)
    return {'project': str(destination), 'run': run_id, 'quota': quota, 'preview_only': manifest['preview_only']}


def merge_receipts(expected, receipts):
    indexed = {}
    for receipt in receipts:
        if receipt['run'] in indexed:
            raise ValueError('Duplicate Cloud backtest receipt')
        if receipt['run'] not in expected:
            raise ValueError('Unexpected Cloud run')
        indexed[receipt['run']] = receipt
    missing = sorted(set(expected) - set(indexed))
    records = [r for run_id in sorted(indexed) for r in indexed[run_id]['records']]
    return {'status': 'PARTIAL' if missing or any(r['status'] != 'PASS' for r in receipts) else 'PASS',
            'missing_runs': missing, 'received_runs': sorted(indexed), 'records': records,
            'merged_hash': digest(records)}


def binding_receipt_dictionary(receipt, frozen):
    expected_code = digest({'snapshots': frozen['snapshot_hashes'], 'templates': frozen['template_hashes']})
    if (receipt.get('origin') != 'quantconnect_cloud_download' or receipt.get('receipt_verified') is not True or
            not receipt.get('backtest_id') or receipt.get('layer') != 'layer1' or
            receipt.get('code_hash') != expected_code):
        return None
    project = HOME / 'work' / receipt['run'] / 'upload-manifest.json'
    if not project.exists():
        raise ValueError('QC identity witness lost its UID dictionary')
    manifest = read(project)
    if manifest['preview_only'] or receipt.get('input_hash') != manifest['run']['input_hash']:
        return None
    return manifest['local_uid_dictionary']


def prepare_bindings():
    """Reuse already accepted local identities when actual dated QC agrees.

    This is not an AI review of every candidate. New official-case investigation
    is reserved for unresolved/conflicting identities, not existing agreements.
    """
    frozen, _ = verify_frozen()
    needed = {s['security_id'] for s in frozen['signals']}
    bindings = {}
    for receipt_path in sorted((HOME / 'results').glob('layer1-*.receipt.json')):
        receipt = read(receipt_path)
        dictionary = binding_receipt_dictionary(receipt, frozen)
        if dictionary is None:
            continue
        for row in receipt['records']:
            for ref in row.get('execution_identity_references', []):
                uid = dictionary[ref['index']]['uid']
                if uid not in needed:
                    continue
                first = min(r['signal_date'] for r in frozen['signals'] if r['security_id'] == uid)
                q, _ = historical_join(frozen['identities'][uid], [ref], first)
                if uid in frozen['accepted_local_candidate_identities'] and q is not None:
                    bindings[uid] = {'method': 'existing_local_qc_agreement', 'qc_sid': q['sid'],
                        'historical_ticker': q['ticker'], 'available_on': first, 'qc_identity': ref,
                        'evidence_path': str(receipt_path), 'evidence_sha256': sha(receipt_path), 'verified_by_rule': True}
    # Previously investigated official cases can supplement conflicting identities.
    spec = importlib.util.spec_from_file_location('srqc_official_evidence', HOME / 'evidence.py')
    evidence_rules = importlib.util.module_from_spec(spec); spec.loader.exec_module(evidence_rules)
    for case_path in sorted((HOME / 'results' / 'official-cases').glob('*.json')):
        case = read(case_path); result = evidence_rules.validate_case(case)
        uid = case['local_uid']
        if uid not in needed or result['evidence_status'] != 'PASS' or not result['asof_selection_usable']:
            continue
        first = min(r['signal_date'] for r in frozen['signals'] if r['security_id'] == uid)
        if case['date'] > first:
            continue
        mappings = [m for m in frozen['identities'][uid]['mappings'] if m['from'] <= first <= (m.get('to') or '9999-12-31')]
        if len(mappings) != 1:
            continue
        bindings[uid] = {'method': 'official_case', 'qc_sid': result['qc_sid'], 'historical_ticker': mappings[0]['ticker'],
            'available_on': case['date'], 'evidence_path': str(case_path), 'evidence_sha256': sha(case_path), 'verified_by_rule': True}
    missing = sorted(needed - set(bindings))
    duplicate_sids = len({b['qc_sid'] for b in bindings.values()}) != len(bindings)
    write(HOME / 'results' / 'accepted-bindings.json', bindings)
    return {'status': 'PASS' if not missing and not duplicate_sids else 'PARTIAL',
            'bindings': len(bindings), 'missing_uids': missing, 'sid_alias_conflicts': duplicate_sids,
            'manual_cases_expected': None, 'master_modified': False}


def import_cloud(project, log, results, backtest_id):
    frozen, _ = verify_frozen()
    manifest = read(Path(project) / 'upload-manifest.json')
    if manifest['preview_only']:
        raise ValueError('Preview project cannot certify actual Cloud validation')
    if not re.fullmatch(r'[A-Za-z0-9_-]{5,100}', backtest_id):
        raise ValueError('Cloud backtest ID required')
    for name, expected in manifest['upload'].items():
        if sha(Path(project) / name) != expected:
            raise ValueError('Uploaded project file changed')
    native = read(results)
    body = native.get('backtest', native)
    if not isinstance(body, dict) or not isinstance(body.get('charts'), dict) or not isinstance(body.get('statistics'), dict):
        raise ValueError('QuantConnect Download Results JSON required, not a test fixture')
    declared_id = body.get('backtestId', native.get('backtestId'))
    if declared_id and str(declared_id) != backtest_id:
        raise ValueError('Downloaded backtest ID mismatch')
    receipt = parse_receipt(Path(log).read_text(encoding='utf-8-sig'), manifest['run'])
    if body.get('errorMessage') or body.get('runtimeError'):
        raise ValueError('QC native results report an execution error')
    if manifest['run']['layer'] in {'layer3', 'layer3-detail'}:
        records = receipt['records']
        if len(records) != 1 or records[0].get('signal_hash') != frozen['signal_hash']:
            raise ValueError('Cloud execution signal receipt mismatch')
        if (records[0].get('sessions_count') != len(frozen['sessions']) or
                records[0].get('sessions_hash') != digest(frozen['sessions'])):
            raise ValueError('Incomplete Cloud execution sessions')
    receipt.update({'origin': 'quantconnect_cloud_download', 'backtest_id': backtest_id,
                    'log_sha256': sha(log), 'native_result_sha256': sha(results),
                    'receipt_verified': True, 'imported_at': datetime.now(timezone.utc).isoformat()})
    target = HOME / 'results' / (receipt['run'] + '.receipt.json')
    if target.exists():
        raise ValueError('Duplicate import; existing Cloud evidence is immutable')
    write(target, receipt)
    if receipt['layer'] == 'smoke':
        state_file = HOME / 'results' / 'smoke-state.json'
        state = read(state_file) if state_file.exists() else {}
        state[receipt['run']] = receipt
        write(state_file, state)
    return {'run': receipt['run'], 'status': receipt['status'], 'smoke_ready': smoke_ready()}


def compare(layer):
    frozen, campaign = verify_frozen()
    expected = [r['id'] for r in campaign['runs'] if r['layer'] == layer]
    receipts = [read(p) for p in sorted((HOME / 'results').glob('*.receipt.json')) if read(p)['layer'] == layer]
    merged = merge_receipts(expected, receipts)
    totals = {c: 0 for c in CLASSES}
    conflicts = []
    for receipt in receipts:
        project = HOME / 'work' / receipt['run']
        dictionary = read(project / 'upload-manifest.json')['local_uid_dictionary'] if project.exists() else {}
        for record in receipt['records']:
            for index, code, reason, rank, flags in record.get('unknown_competitors', []):
                if not 0 <= code < 5 or index not in dictionary:
                    raise ValueError('Unknown competitor interpretation/schema')
                category = ['QC Confirms Out', 'QC Confirms In', 'QC Borderline',
                            'QC Identity / Lifecycle Conflict', 'QC Coverage Unknown'][code]
                totals[category] += 1
                if code in {1, 2, 3}:
                    conflicts.append({'local_uid': dictionary[index]['uid'], 'date': record['date'],
                                      'qc_classification': category, 'qc_rank': rank, 'reason_code': reason,
                                      'assessment_flags': flags})
    merged['unknown_day_classifications'] = totals
    merged['official_evidence_queue'] = sorted(conflicts, key=lambda r: (r['date'], r['local_uid']))
    if layer == 'layer3':
        merged['local_native_baseline'] = 'NOT_RUN'
        merged['comparison_status'] = 'BASELINE_NOT_RUN_NO_CURRENT_FALLBACK'
        merged['metric_differences'] = None
    write(HOME / 'results' / (layer + '-comparison.json'), merged)
    return {k: v for k, v in merged.items() if k != 'records'}


def execution_comparison(cloud_receipt, native_result, local_baseline, frozen_signal_hash):
    """Compare actual derived fills/trades without using Current as a PIT baseline.

    Local baseline is a validation-only JSON envelope around existing Native
    artifacts, with hashes, source signal hash and completed scoped gate proof.
    It is never generated from Current results. No market bars are accepted.
    """
    if local_baseline is None:
        return {'status': 'BASELINE_NOT_RUN', 'differences': None}
    if (local_baseline.get('engine') != 'lean' or local_baseline.get('universe_mode') != 'point_in_time'
            or local_baseline.get('native_status') != 'PASS'
            or local_baseline.get('signal_hash') != frozen_signal_hash
            or local_baseline.get('scoped_gates_pass') is not True):
        raise ValueError('Actual hash-bound PIT Native baseline required; no Current fallback')
    cloud = cloud_receipt['records'][0]
    if cloud.get('type') != 'execution' or cloud.get('signal_hash') != frozen_signal_hash:
        raise ValueError('Cloud frozen execution signal hash mismatch')
    metric_names = ['trade_count', 'win_rate', 'average_trade', 'final_equity', 'total_return',
                    'max_drawdown', 'fees', 'turnover', 'remaining_holdings']
    differences = {}
    for key in metric_names:
        left, right = local_baseline['metrics'].get(key), cloud['metrics'].get(key)
        differences[key] = {'local': left, 'qc': right, 'delta': right - left if left is not None and right is not None else None}
    body = native_result.get('backtest', native_result)
    orders = body.get('orders', {})
    qc_orders = list(orders.values()) if isinstance(orders, dict) else list(orders)
    # Download Results native orders retain time, SID, fill/order economics and tags.
    fields = ['time', 'symbol', 'quantity', 'price', 'status', 'tag', 'orderFee']
    local_orders = local_baseline.get('orders', [])
    order_differences = []
    for n in range(max(len(local_orders), len(qc_orders))):
        left = local_orders[n] if n < len(local_orders) else None
        right = qc_orders[n] if n < len(qc_orders) else None
        if left is None or right is None:
            order_differences.append({'ordinal': n, 'local': left, 'qc': right})
        else:
            delta = {key: [left.get(key), right.get(key)] for key in fields if left.get(key) != right.get(key)}
            if delta:
                order_differences.append({'ordinal': n, 'differences': delta})
    return {'status': 'REVIEW_REQUIRED' if order_differences or any(v['delta'] != 0 for v in differences.values()) else 'OBSERVED_EQUAL',
            'differences': differences, 'orders': {'local_count': len(local_orders), 'qc_count': len(qc_orders),
            'mismatches': order_differences}, 'corporate_actions': cloud.get('actions', []),
            'local_corporate_actions': local_baseline.get('actions', []),
            'fill_detail_status': 'AVAILABLE' if body.get('orderEvents') else 'NEEDS_NATIVE_CSV_OR_EXECUTION_DETAIL_BUCKETS',
            'model_differences': cloud.get('model_differences', []),
            'acceptance': 'Does not replace scoped PIT/native/reconciliation gates'}


def merge_execution_details(summary_receipt, details):
    summary = summary_receipt['records'][0]
    if summary.get('type') != 'execution':
        raise ValueError('Execution summary required')
    buckets, fills, trades = set(), {}, {}
    for receipt in details:
        if receipt.get('origin') != 'quantconnect_cloud_download' or len(receipt['records']) != 1:
            raise ValueError('Actual execution detail receipt required')
        record = receipt['records'][0]
        bucket = record.get('bucket')
        if record.get('type') != 'execution_details' or record.get('buckets') != 128 or bucket in buckets:
            raise ValueError('Duplicate/unexpected execution bucket')
        buckets.add(bucket)
        for key in ['signal_hash', 'fills_hash', 'trades_hash', 'sessions_hash']:
            if record.get(key) != summary.get(key):
                raise ValueError('Rerun economics differ from original execution summary')
        for name, destination in [('fills', fills), ('trades', trades)]:
            for ordinal, row in record[name]:
                if ordinal in destination or ordinal % 128 != bucket:
                    raise ValueError('Duplicate/misplaced execution detail')
                destination[ordinal] = row
    missing = sorted(set(range(128)) - buckets)
    if missing:
        return {'status': 'PARTIAL', 'missing_buckets': missing}
    result = {'status': 'PASS', 'fills': [fills[n] for n in sorted(fills)], 'trades': [trades[n] for n in sorted(trades)]}
    if len(result['fills']) != summary['fills_count'] or digest(result['fills']) != summary['fills_hash'] or digest(result['trades']) != summary['trades_hash']:
        raise ValueError('Merged execution fills/trades are incomplete')
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('prepare')
    sub.add_parser('verify')
    sub.add_parser('quota')
    sub.add_parser('bindings')
    stage_parser = sub.add_parser('stage')
    stage_parser.add_argument('--run', required=True)
    stage_parser.add_argument('--preview', action='store_true')
    importer = sub.add_parser('import')
    for name in ['project', 'log', 'results', 'backtest-id']:
        importer.add_argument('--' + name, required=True)
    comparator = sub.add_parser('compare')
    comparator.add_argument('--layer', choices=['layer1', 'layer2', 'layer3'], required=True)
    execution_parser = sub.add_parser('compare-execution')
    execution_parser.add_argument('--cloud-receipt', required=True)
    execution_parser.add_argument('--results', required=True)
    execution_parser.add_argument('--local-baseline', required=True)
    detail_parser = sub.add_parser('merge-execution-details')
    detail_parser.add_argument('--summary', required=True)
    detail_parser.add_argument('--details-directory', required=True)
    args = parser.parse_args()
    if args.command == 'prepare':
        result = prepare()
    elif args.command == 'verify':
        frozen, campaign = verify_frozen()
        result = {'frozen_hash': campaign['frozen_hash'], 'signal_hash': frozen['signal_hash'], 'verified': True}
    elif args.command == 'quota':
        result = audit_all_quotas()
        result.pop('rows')
    elif args.command == 'bindings':
        result = prepare_bindings()
    elif args.command == 'stage':
        result = stage(args.run, preview=args.preview)
    elif args.command == 'import':
        result = import_cloud(args.project, args.log, args.results, args.backtest_id)
    elif args.command == 'merge-execution-details':
        files = sorted(Path(args.details_directory).glob('layer3-detail-*.receipt.json'))
        result = merge_execution_details(read(args.summary), [read(p) for p in files])
        write(HOME / 'results' / 'execution-details.json', result)
    elif args.command == 'compare-execution':
        frozen, _ = verify_frozen()
        result = execution_comparison(read(args.cloud_receipt), read(args.results),
                                      read(args.local_baseline), frozen['signal_hash'])
        write(HOME / 'results' / 'execution-comparison.json', result)
    else:
        result = compare(args.layer)
    print(json.dumps(result, ensure_ascii=True, indent=2))


if __name__ == '__main__':
    main()

"""Validation harness tests are offline fixtures, never actual Cloud receipts."""
import ast
import copy
import importlib.util
import json
from pathlib import Path
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
QV = ROOT / 'quantconnect-validation'
sys.path.insert(0, str(QV / 'cloud'))
spec = importlib.util.spec_from_file_location('stock_radar_qc_validation', QV / 'local.py')
local = importlib.util.module_from_spec(spec)
spec.loader.exec_module(local)
from protocol import canonical, digest, historical_join, membership_summary, parse_receipt, receipt_lines
requires_local_cache = pytest.mark.skipif(
    not (ROOT / 'data/pit/research-grade/scanner-C.json').exists(),
    reason='PIT physical-cache integration; pure harness tests still run on a fresh clone')


def run(layer='layer1'):
    return {'id': 'offline-test', 'layer': layer, 'dates': ['2024-09-30'],
            'input_hash': 'a' * 64, 'code_hash': 'b' * 64}


def identity():
    return {'uid': 'local-1', 'mappings': [{'ticker': 'OLD', 'from': '2020-01-01',
                'to': '2024-12-31', 'class': 'CLASS-A'}],
            'issuers': [{'cik': '1234', 'available_on': '2024-01-01'}]}


def qc(**overrides):
    return {'sid': 'SID-1', 'ticker': 'OLD', 'as_of': '2024-09-30',
            'cik': '0000001234', 'class': 'CLASS-A', **overrides}


def test_free_file_size_quota_utf8_bytes():
    with pytest.raises(ValueError, match='file-size'):
        local.check_quota({'x.py': '# ' + '\u4e2d' * 11000})
    assert local.check_quota({'x.py': '# small'})['reserved_notebook'] == 1


def test_free_file_count_reserves_default_notebook():
    with pytest.raises(ValueError, match='file-count'):
        local.check_quota({f'f{n}.py': '' for n in range(25)})


def test_compact_output_quota_refuses_silent_truncation():
    with pytest.raises(ValueError, match='too large'):
        receipt_lines(run(), [{'type': 'membership', 'date': '2024-09-30', 'ids': ['id'] * 3000}], 'PARTIAL')


def test_parser_timestamp_prefix_and_round_trip():
    rows = [{'type': 'membership', 'date': '2024-09-30', 'qc_count': 1000}]
    lines = receipt_lines(run(), rows, 'PARTIAL')
    parsed = parse_receipt('\n'.join('2024-09-30 16:00:00 ' + l for l in lines), run())
    assert parsed['records'] == rows and parsed['status'] == 'PARTIAL'


@pytest.mark.parametrize('field', ['input_hash', 'code_hash', 'dates'])
def test_parser_frozen_header_drift(field):
    changed = run(); changed[field] = 'changed'
    with pytest.raises(ValueError, match='Frozen receipt'):
        parse_receipt('\n'.join(receipt_lines(run(), [], 'FAIL')), changed)


def test_missing_log_trailer_and_duplicate_sequence():
    lines = receipt_lines(run(), [{'type': 'membership', 'date': '2024-09-30'}], 'PARTIAL')
    with pytest.raises(ValueError, match='begin/end'):
        parse_receipt('\n'.join(lines[:-1]), run())
    with pytest.raises(ValueError, match='sequence'):
        parse_receipt('\n'.join(lines[:2] + [lines[1]] + lines[2:]), run())


def test_missing_daily_result_is_not_zero():
    with pytest.raises(ValueError, match='Daily observations'):
        parse_receipt('\n'.join(receipt_lines(run(), [], 'FAIL')), run())


def test_membership_comparison_identity_bounds():
    s = membership_summary(1000, 1000, range(900), range(900), 25)
    assert s['intersection'] == 900 and s['local_only_upper'] == 100
    assert s['jaccard_lower'] == pytest.approx(900 / 1100)
    assert s['jaccard_upper'] == pytest.approx(925 / 1075)
    assert not s['definitive']


def test_identity_join_requires_dated_issuer_and_class():
    assert historical_join(identity(), [qc()], '2024-09-30')[0]['sid'] == 'SID-1'
    assert historical_join(identity(), [qc(cik='9999')], '2024-09-30')[0] is None
    assert historical_join(identity(), [qc(**{'class': 'CLASS-B'})], '2024-09-30')[0] is None


def test_no_current_symbol_backfill():
    assert historical_join(identity(), [qc(ticker='NEW')], '2024-09-30')[0] is None
    assert historical_join(identity(), [qc(as_of='2026-10-07')], '2024-09-30')[0] is None


def test_future_issuer_fact_and_listing_cannot_validate_old_identity():
    value = identity(); value['issuers'][0]['available_on'] = '2025-01-01'
    assert historical_join(value, [qc()], '2024-09-30')[0] is None
    assert historical_join(identity(), [qc(listing_date='2025-01-01')], '2024-09-30')[0] is None


def test_reused_ticker_and_multiple_classes_remain_conflicts():
    value = identity(); value['mappings'].append(copy.deepcopy(value['mappings'][0]))
    assert historical_join(value, [qc()], '2024-09-30')[0] is None
    value = identity(); value['mappings'][0]['class'] = 'COMMON'
    assert historical_join(value, [qc(**{'class': 'COMMON'}), qc(ticker='OTHER', sid='SID-2', **{'class': 'COMMON'})],
                           '2024-09-30')[0] is None


def test_chunk_merge_deterministic_and_missing_duplicate_detection():
    a = {'run': 'a', 'records': [{'count': 1}], 'status': 'PASS'}
    b = {'run': 'b', 'records': [{'count': 2}], 'status': 'PASS'}
    assert local.merge_receipts(['a', 'b'], [a, b]) == local.merge_receipts(['a', 'b'], [b, a])
    assert local.merge_receipts(['a', 'b'], [a])['missing_runs'] == ['b']
    with pytest.raises(ValueError, match='Duplicate'):
        local.merge_receipts(['a'], [a, a])


@requires_local_cache
def test_strategy_parameter_and_snapshot_drift_checks():
    frozen, campaign = local.verify_frozen()
    import yaml
    assert frozen['common']['strategy'] == yaml.safe_load((ROOT / 'strategies/full_strategy2_v1/strategy.yaml').read_text(encoding='utf8'))
    for name, source in local.SOURCES.items():
        expected = local.snapshot_source(name, (ROOT / source).read_text(encoding='utf8'))
        assert expected == (QV / 'snapshots' / (name + '.py')).read_text(encoding='utf8')


@requires_local_cache
def test_snapshot_selector_matches_production_plugin_on_real_causal_rows():
    sys.path.insert(0, str(QV / 'snapshots'))
    from qc_adapter import evaluate_selection as cloned
    from qc_plugin import PLUGIN
    from radar.strategy.adapter import evaluate_selection
    from radar.strategy.loader import load_strategy_directory
    frozen, _ = local.verify_frozen()
    data = json.loads((ROOT / 'data/pit/research-grade/scanner-C.json').read_text(encoding='utf8'))
    day = data['rows'][0]['signal_date']
    rows = [{**r['features'], 'date': pd.Timestamp(day), 'symbol': r['symbol'], 'security_name': r['symbol']}
            for r in data['rows'] if r['signal_date'] == day]
    frame = pd.DataFrame(rows)
    original = load_strategy_directory(ROOT / 'strategies/full_strategy2_v1', set(frame.columns), run_tests=False)
    # Loader result shape follows repository contract; actual plugin is source-generated too.
    plugin = original.plugin if hasattr(original, 'plugin') else original[1]
    expected, _ = evaluate_selection(plugin, frozen['common']['strategy'], frame)
    actual, _ = cloned(PLUGIN, frozen['common']['strategy'], frame)
    pd.testing.assert_frame_equal(expected, actual)


@requires_local_cache
def test_snapshot_core_lag_missingness_and_future_invariance():
    sys.path.insert(0, str(QV / 'snapshots'))
    from qc_core import core_membership
    from radar.pit.research import core_membership as original
    frozen, _ = local.verify_frozen()
    calendar = [str(d.date()) for d in pd.bdate_range('2024-01-01', periods=128)]
    bars = pd.DataFrame({'date': calendar[:127], 'security_id': 'x', 'open': 10., 'high': 11.,
                         'low': 9., 'close': 10., 'volume': 3000000.})
    members = [{'security_id': 'x', 'security_type': 'common'}]
    args = (calendar[-1], members, bars, calendar, frozen['common']['core_rules'])
    assert core_membership(*args) == original(*args)
    assert core_membership(*args)['security_ids'] == ['x']
    future = pd.concat([bars, bars.iloc[-1:].assign(date='2030-01-01', close=1e8)])
    assert core_membership(calendar[-1], members, future, calendar, frozen['common']['core_rules']) == original(*args)
    gap = bars.drop(index=20)
    assert core_membership(calendar[-1], members, gap, calendar, frozen['common']['core_rules'])['unknown_security_ids'] == ['x']


@requires_local_cache
def test_frozen_signal_hash_and_no_labels():
    frozen, _ = local.verify_frozen()
    assert local.check_signals(frozen['signals']) == frozen['signal_hash']
    assert len(frozen['signals']) == 1264
    modified = copy.deepcopy(frozen['signals']); modified[0]['future_return'] = .5
    with pytest.raises(ValueError, match='drift/future'):
        local.check_signals(modified)
    modified = copy.deepcopy(frozen['signals']); modified[0]['rank'] += 1
    assert local.check_signals(modified) != frozen['signal_hash']


def test_no_current_native_fallback():
    with pytest.raises(ValueError, match='no Current fallback'):
        local.execution_comparison({}, {}, {'engine': 'lean', 'universe_mode': 'current'}, 'a' * 64)
    assert local.execution_comparison({}, {}, None, 'a' * 64)['status'] == 'BASELINE_NOT_RUN'


def test_raw_qc_market_export_refused():
    with pytest.raises(ValueError, match='raw market'):
        receipt_lines(run(), [{'nested': {'bars': [{'close': 5}]}}], 'PARTIAL')
    for name in ['main_validation.py', 'smoke.py', 'execution_adapter.py']:
        text = (QV / 'cloud' / name).read_text(encoding='utf8')
        assert 'object_store.save' not in text and '.to_csv' not in text


def test_cloud_smoke_expected_schema_and_false_pass():
    checks = dict.fromkeys(['history_access', 'stable_control', 'security_master', 'mapping', 'split_history'], True)
    records = [{'type': 'smoke', 'checks': checks}]
    assert parse_receipt('\n'.join(receipt_lines(run('smoke'), records, 'PASS')), run('smoke'))['status'] == 'PASS'
    checks['mapping'] = False
    with pytest.raises(ValueError, match='False smoke'):
        parse_receipt('\n'.join(receipt_lines(run('smoke'), records, 'PASS')), run('smoke'))


@requires_local_cache
def test_preview_layer_cannot_run_without_real_cloud_smoke():
    frozen, campaign = local.verify_frozen()
    assert not local.smoke_ready()
    with pytest.raises(ValueError, match='BOTH real Cloud'):
        local.project_input(frozen, campaign['runs'][2], preview=False)


@requires_local_cache
def test_project_input_does_not_mutate_dated_source():
    frozen, campaign = local.verify_frozen()
    original = digest(frozen)
    local.project_input(frozen, campaign['runs'][2], preview=True)
    assert digest(frozen) == original


@requires_local_cache
def test_all_prepared_projects_fit_quota_and_have_no_cloud_pass():
    manifests = list((QV / 'projects').glob('*/upload-manifest.json')) + list((QV / 'work').glob('*/upload-manifest.json'))
    assert len(manifests) >= 5
    for path in manifests:
        m = local.read(path)
        files = {name: (path.parent / name).read_text(encoding='utf8') for name in m['upload']}
        assert local.check_quota(files) == m['quota']
        assert m['cloud_executed'] is False


def test_official_evidence_never_accepts_ai_text_or_future_asof_fact():
    spec = importlib.util.spec_from_file_location('qc_evidence', QV / 'evidence.py')
    evidence = importlib.util.module_from_spec(spec); spec.loader.exec_module(evidence)
    case = {k: None for k in evidence.REQUIRED}
    case.update({'date': '2024-09-30', 'use': 'asof_decision', 'official_evidence': [], 'issuer_cik': '0000001234', 'share_class': 'CLASS-A'})
    assert evidence.validate_case(case)['evidence_status'] == 'FAIL'
    case['official_evidence'] = [{'url': 'https://www.sec.gov/' + str(n), 'publisher_type': 'SEC',
        'source_date': '2025-01-01', 'published_at': '2025-01-01', 'captured_sha256': 'a' * 64,
        'issuer_cik': '0000001234', 'share_class': 'CLASS-A', 'assertion': 'An AI says PASS', 'supports_qc_sid': 'SID-1'} for n in range(2)]
    assert evidence.validate_case(case)['evidence_status'] == 'FAIL'


def test_smoke_resolves_reused_ticker_at_historical_date():
    # A current-date string subscription resolves a different issuer for reused FB.
    from datetime import datetime
    from types import SimpleNamespace
    tree = ast.parse((QV / 'cloud/smoke.py').read_text(encoding='utf8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    initialize = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'initialize')
    generated, subscribed = [], []

    def generate(ticker, market, *, mapping_resolve_date):
        generated.append((ticker, market, mapping_resolve_date))
        return ticker + '-historical-issuer'

    def subscribe(symbol, resolution, **kwargs):
        assert symbol.id.endswith('-historical-issuer')
        assert kwargs == {'fill_forward': False, 'data_normalization_mode': 'raw'}
        subscribed.append(symbol)
        return SimpleNamespace(symbol=symbol)

    scope = {'datetime': datetime, 'RUN': {'id': 'smoke-mapping', 'case': 'FB',
        'dates': ['2022-06-06', '2022-06-14']},
        'SecurityIdentifier': SimpleNamespace(generate_equity=generate),
        'Symbol': lambda sid, ticker: SimpleNamespace(id=sid, value=ticker),
        'Market': SimpleNamespace(USA='usa'), 'Resolution': SimpleNamespace(DAILY='daily'),
        'DataNormalizationMode': SimpleNamespace(RAW='raw'),
        'TimeZones': SimpleNamespace(NEW_YORK='new_york'),
        'Universe': SimpleNamespace(UNCHANGED='unchanged')}
    exec(compile(ast.Module(body=[initialize], type_ignores=[]), '<historical subscription fixture>', 'exec'), scope)
    no_op = lambda *args: None
    algo = SimpleNamespace(settings=SimpleNamespace(), universe_settings=SimpleNamespace(),
        set_name=no_op, set_start_date=no_op, set_end_date=no_op, set_time_zone=no_op,
        set_cash=no_op, add_universe=no_op, add_security=subscribe)
    scope['initialize'](algo)
    assert len(subscribed) == 3
    assert generated[-1] == ('FB', 'usa', datetime(2022, 6, 6))
    assert algo._symbols['FB'].id == 'FB-historical-issuer'


def test_cloud_debug_cap_does_not_truncate_download_receipt():
    from datetime import datetime
    from types import SimpleNamespace
    from protocol import normalize_cik
    tree = ast.parse((QV / 'cloud/smoke.py').read_text(encoding='utf8'))
    cls = next(n for n in tree.body if isinstance(n, ast.ClassDef))
    end = next(n for n in cls.body if isinstance(n, ast.FunctionDef) and n.name == 'on_end_of_algorithm')
    fixture_run = dict(run('smoke'), case='FB', dates=['2022-06-06', '2022-06-13'])
    scope = {'RUN': fixture_run, 'datetime': datetime, 'canonical': canonical,
        'normalize_cik': normalize_cik, 'receipt_lines': receipt_lines,
        'raw_frames': lambda *args: {'FB': [1, 2, 3], 'MSFT': [1, 2, 3]},
        'Resolution': SimpleNamespace(DAILY='daily'), 'Split': object,
        'SplitType': SimpleNamespace(SPLIT_OCCURRED='occurred')}
    exec(compile(ast.Module(body=[end], type_ignores=[]), '<Cloud log transport fixture>', 'exec'), scope)
    case = SimpleNamespace(id='SID-FB')
    fundamental = SimpleNamespace(symbol=case, company_reference=SimpleNamespace(cik='1234'),
        security_reference=SimpleNamespace(security_type='ST00000001'))

    class History:
        def __call__(self, *args):
            return {'historical': [fundamental]}
        def __getitem__(self, type_):
            return lambda *args: []

    logs, debug = [], []
    algo = SimpleNamespace(_symbols={'FB': case, 'MSFT': SimpleNamespace(id='SID-MSFT')},
        _seen={'SID-FB': {'2022-06-06', '2022-06-07', '2022-06-08'}},
        _mapping=[['SID-FB', 'FB', 'META', '2022-06-09']], _splits=[], _universe='historical',
        time=datetime(2022, 6, 14), history=History(), log=logs.append,
        debug=lambda message: debug.append(message[:200]))
    scope['on_end_of_algorithm'](algo)
    assert any(len(line) > 200 for line in logs)
    assert len(debug) == 1 and len(debug[0]) < 200
    assert json.loads(debug[0].removeprefix('SRQC_SMOKE '))['status'] == 'PASS'
    receipt = parse_receipt('\n'.join(logs + debug), fixture_run)
    assert receipt['status'] == 'PASS' and receipt['records'][0]['mapping_events'][0][2] == 'META'


def test_every_date_not_just_first_date_fits_free_file_count():
    audit = local.read(QV / 'quota-audit.json')
    assert audit['status'] == 'PASS' and audit['checked_date_projects'] == 470
    assert audit['max_with_default_notebook'] <= 25
    assert audit['max_project_file_bytes'] <= 32000
    assert {r['run'].split('-')[1] for r in audit['rows']} >= {'2024', '2025'}


def test_execution_detail_merge_requires_all_buckets_and_same_economics():
    fills, trades = [{'quantity': 1, 'fill_price': 5}], []
    summary = {'records': [{'type': 'execution', 'signal_hash': 'a', 'sessions_hash': 'b',
                'fills_hash': digest(fills), 'trades_hash': digest(trades), 'fills_count': 1}]}
    records = []
    for bucket in range(128):
        records.append({'origin': 'quantconnect_cloud_download', 'records': [{
            'type': 'execution_details', 'bucket': bucket, 'buckets': 128, 'signal_hash': 'a', 'sessions_hash': 'b',
            'fills_hash': digest(fills), 'trades_hash': digest(trades),
            'fills': [[0, fills[0]]] if bucket == 0 else [], 'trades': []}]})
    assert local.merge_execution_details(summary, records)['fills'] == fills
    assert local.merge_execution_details(summary, records[:-1])['status'] == 'PARTIAL'
    with pytest.raises(ValueError, match='Duplicate'):
        local.merge_execution_details(summary, records + [records[0]])
    changed = copy.deepcopy(records); changed[1]['records'][0]['fills_hash'] = 'changed'
    with pytest.raises(ValueError, match='economics differ'):
        local.merge_execution_details(summary, changed)


@pytest.mark.parametrize('qc_unknown,expected', [(0, 1), (100, 1), (900, 4)])
def test_qc_in_requires_worst_rank_to_fit_cap(qc_unknown, expected):
    # Exercise the Cloud decision function without loading LEAN or claiming a Cloud run.
    tree = ast.parse((QV / 'cloud/membership.py').read_text(encoding='utf8'))
    function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'compare_membership')
    scope = {'digest': digest, 'historical_join': historical_join, 'membership_summary': membership_summary}
    exec(compile(ast.Module(body=[function], type_ignores=[]), '<offline QC decision fixture>', 'exec'), scope)
    core = {'security_ids': ['SID-1'] + ['other' + str(n) for n in range(999)],
            'unknown_security_ids': ['unknown' + str(n) for n in range(qc_unknown)], 'population_type_unknown': 0,
            'rank': {'SID-1': 300}, 'rejected': {}, 'assessment': {'SID-1': 63}}
    inputs = {'core': [], 'unknown': ['0'], 'identities': {'0': identity()}}
    record, _ = scope['compare_membership']([qc()], core, inputs, '2024-09-30')
    assert record['unknown_competitors'][0][1] == expected


@pytest.mark.parametrize('case,expected', [('agreement', 1), ('unresolved_local', 0),
    ('changed_qc_issuer', 0), ('future_qc_identity', 0), ('fixture_origin', 0), ('stale_code', 0)])
def test_binding_reuses_only_accepted_local_identity_and_actual_dated_qc(case, expected, tmp_path, monkeypatch):
    frozen = {'snapshot_hashes': {}, 'template_hashes': {}, 'signals': [
        {'security_id': 'local-1', 'signal_date': '2024-09-30'}],
        'identities': {'local-1': identity()}, 'accepted_local_candidate_identities': {
            'local-1': {'pass': True, 'level': 'A'}}}
    reference = {'index': '0', **qc()}
    receipt = {'run': 'layer1-2024-09-30', 'layer': 'layer1', 'origin': 'quantconnect_cloud_download',
        'backtest_id': 'offline-fixture-id', 'receipt_verified': True, 'input_hash': 'fixture-input',
        'code_hash': digest({'snapshots': {}, 'templates': {}}),
        'records': [{'date': '2024-09-30', 'execution_identity_references': [reference]}]}
    if case == 'unresolved_local':
        frozen['accepted_local_candidate_identities'] = {}
    elif case == 'changed_qc_issuer':
        reference['cik'] = '9999999999'
    elif case == 'future_qc_identity':
        reference['as_of'] = '2024-10-01'
    elif case == 'fixture_origin':
        receipt['origin'] = 'offline_test_fixture'
    elif case == 'stale_code':
        receipt['code_hash'] = 'old-campaign'
    monkeypatch.setattr(local, 'HOME', tmp_path)
    monkeypatch.setattr(local, 'verify_frozen', lambda: (frozen, {}))
    (tmp_path / 'evidence.py').write_text((QV / 'evidence.py').read_text(encoding='utf8'), encoding='utf8')
    local.write(tmp_path / 'results' / 'layer1-2024-09-30.receipt.json', receipt)
    local.write(tmp_path / 'work' / receipt['run'] / 'upload-manifest.json', {
        'preview_only': False, 'run': {'input_hash': 'fixture-input'}, 'local_uid_dictionary': {'0': {'uid': 'local-1'}}})
    result = local.prepare_bindings()
    assert result['bindings'] == expected
    assert result['manual_cases_expected'] is None and result['master_modified'] is False
    bindings = local.read(tmp_path / 'results' / 'accepted-bindings.json')
    if expected:
        assert bindings['local-1']['method'] == 'existing_local_qc_agreement'
        assert result['status'] == 'PASS'
    else:
        assert result['status'] == 'PARTIAL' and result['missing_uids'] == ['local-1']

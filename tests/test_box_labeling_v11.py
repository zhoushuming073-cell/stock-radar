"""Versioned ontology, blind view and immutable annotation namespace."""
import json

import pytest

from radar.box_labeling.dataset import packed
from radar.box_labeling.ontology_v11 import BoxStoreV11, LABEL_VERSION, validate
from radar.box_labeling.store import BoxStore, GateError, digest


def bundle(tmp_path):
    root = tmp_path / 'private-box-fixture'
    (root / 'charts').mkdir(parents=True)
    (root / 'raw').mkdir()
    chart = b'<svg xmlns="http://www.w3.org/2000/svg"><title>historical</title></svg>'
    raw = packed([['2024-01-01', 100, 105, 95, 100, 1000],
                  ['2024-01-02', 101, 108, 96, 104, 1200]])
    (root / 'charts' / 'chart.svg').write_bytes(chart)
    (root / 'raw' / 'raw.json').write_bytes(raw)
    row = {'task_id': 'opaque-task', 'security_id': 'private-security',
           'decision_date': '2024-01-02', 'split': 'train', 'stratum': 'positive',
           'candidate_score': .8, 'candidate_plugin_version': 'fixture',
           'config_hash': 'fixture', 'normalization_version': 'fixture',
           'scales': {'daily': {'chart_file': 'chart.svg', 'chart_hash': digest(chart),
                                'raw_file': 'raw.json', 'raw_hash': digest(raw),
                                'tensor_hash': 'fixture', 'length': 2}}}
    manifest = packed([row])
    (root / 'manifest.json').write_bytes(manifest)
    (root / 'receipt.json').write_bytes(packed({'version': 'box-label-tasks-v1',
                                               'manifest_hash': digest(manifest)}))
    return root


def label(**overrides):
    result = {'shape': 'BOX', 'position': 'LOWER', 'subtype': 'SIDEWAYS_RANGE',
              'confidence': 'MEDIUM', 'reasons': ['REPEATED_LOWER_TOUCH'],
              'note': '', 'evidence_start': 5, 'lower_pct': -7.5,
              'upper_pct': 8.0, 'expected_revision': 0,
              'label_version': LABEL_VERSION}
    result.update(overrides)
    return result


def test_v11_null_and_conditional_contract():
    assert validate(label())['shape'] == 'BOX'
    assert validate(label(shape='NOT_BOX', position='BREAKDOWN',
                          subtype='PERSISTENT_BREAKDOWN', lower_pct=None,
                          upper_pct=None))['shape'] == 'NOT_BOX'
    assert validate(label(shape='UNCERTAIN', position='UNCERTAIN',
                          subtype='UNDECIDABLE', evidence_start=None,
                          lower_pct=None, upper_pct=None))['shape'] == 'UNCERTAIN'
    invalid = [label(label_version='box-structure-label-v1'),
               label(evidence_start=42), label(evidence_start=True),
               label(lower_pct=None), label(lower_pct=float('nan')),
               label(upper_pct=-9), label(reasons=['DRIFT', 'DRIFT']),
               label(shape='NOT_BOX'), label(shape='UNCERTAIN'),
               label(shape='BOX', subtype='MONOTONIC_TREND'),
               label(unknown='unexpected')]
    for item in invalid:
        with pytest.raises(GateError):
            validate(item)


def test_v11_private_view_and_namespace_isolation(tmp_path):
    root = bundle(tmp_path)
    old = BoxStore(root, 'human')
    human = BoxStoreV11(root, 'human')
    smoke = BoxStoreV11(root, 'smoke')
    view = human.task('opaque-task', 1)
    assert view['label_version'] == LABEL_VERSION
    assert view['view_renderer_version'] == 'box-svg-percent-axis-v1.1'
    assert '+3.8%' in view['charts']['daily']
    assert 'private-security' not in json.dumps(view)
    assert '2024-01-02' not in json.dumps(view)
    assert 'candidate_score' not in json.dumps(view)
    assert human.save('opaque-task', 1, label())['revision'] == 1
    assert human.task('opaque-task', 1)['label']['lower_pct'] == -7.5
    assert old.task('opaque-task', 1)['revision'] == 0
    assert smoke.task('opaque-task', 1)['revision'] == 0
    assert human.save('opaque-task', 1, label(expected_revision=1,
                                                 position='MIDDLE'))['revision'] == 2
    with pytest.raises(GateError, match='stale'):
        human.save('opaque-task', 1, label())
    assert human.skip('opaque-task', 1) == {'skipped': True}
    assert sorted(p.name for p in root.glob('annotations*.sqlite3')) == [
        'annotations-human.sqlite3', 'annotations-v1.1-human.sqlite3',
        'annotations-v1.1-smoke.sqlite3']


def test_v11_chart_hash_gate_and_no_real_label_export(tmp_path):
    root = bundle(tmp_path)
    human = BoxStoreV11(root, 'human')
    (root / 'raw' / 'raw.json').write_bytes(b'[]')
    with pytest.raises(GateError, match='drift'):
        human.task('opaque-task', 1)
    with pytest.raises(GateError, match='separately approved'):
        human.export_numeric(1, root / 'training.json')
    assert not (root / 'training.json').exists()

"""Blind human box annotation contract v1.1. No market data or outcomes."""
import math
import json
from xml.etree import ElementTree as ET

from .store import BoxStore, GateError, digest

LABEL_VERSION = 'box-structure-label-v1.1'
SHAPES = {'BOX', 'NOT_BOX', 'UNCERTAIN'}
POSITIONS = {'LOWER', 'MIDDLE', 'UPPER', 'BREAKDOWN', 'UNCERTAIN'}
CONFIDENCES = {'HIGH', 'MEDIUM', 'LOW'}
SUBTYPES = {'SIDEWAYS_RANGE', 'DRIFTING_CHANNEL', 'NOISY_CONSOLIDATION',
            'MONOTONIC_TREND', 'TRANSIENT_UNDERCUT_RECOVERY',
            'PERSISTENT_BREAKDOWN', 'INSUFFICIENT_HISTORY', 'UNDECIDABLE'}
REASONS = {'REPEATED_LOWER_TOUCH', 'REPEATED_UPPER_TOUCH', 'RANGE_DURABILITY',
           'DRIFT', 'NOISY', 'UNDERCUT_RECOVERED', 'BREAKDOWN_PERSISTS',
           'TOO_FEW_TOUCHES', 'TREND_DOMINATES', 'SCALE_DISAGREEMENT',
           'INSUFFICIENT_HISTORY'}
FIELDS = {'shape', 'position', 'confidence', 'subtype', 'reasons', 'note',
          'evidence_start', 'lower_pct', 'upper_pct', 'expected_revision',
          'label_version'}
VIEW_RENDERER_VERSION = 'box-svg-percent-axis-v1.1'


def percent_axis(svg, raw):
    """Add a relative-price reading aid without exposing absolute price or identity."""
    bars = json.loads(raw)
    if not bars or any(len(bar) != 6 for bar in bars):
        raise GateError('invalid raw chart series')
    low = min(float(bar[3]) for bar in bars)
    high = max(float(bar[2]) for bar in bars)
    close = float(bars[-1][4])
    if not 0 < low <= high or not 0 < close:
        raise GateError('invalid chart price range')
    root = ET.fromstring(svg)
    namespace = '{http://www.w3.org/2000/svg}'
    for fraction in (0, .25, .5, .75, 1):
        price = high - fraction * (high - low)
        ET.SubElement(root, namespace + 'text', x='1', y=f'{20 + 245 * fraction:.1f}',
                      fill='#475569', **{'font-size': '11'}).text = f'{100 * (price / close - 1):+.1f}%'
    return ET.tostring(root, encoding='unicode')


def validate(payload):
    if not isinstance(payload, dict) or set(payload) != FIELDS:
        raise GateError('invalid v1.1 label fields')
    if payload['label_version'] != LABEL_VERSION:
        raise GateError('invalid v1.1 label version')
    if (payload['shape'] not in SHAPES or payload['position'] not in POSITIONS
            or payload['confidence'] not in CONFIDENCES
            or payload['subtype'] not in SUBTYPES):
        raise GateError('invalid v1.1 label choice')
    if payload['shape'] == 'UNCERTAIN' and payload['position'] != 'UNCERTAIN':
        raise GateError('uncertain shape requires uncertain position')
    if payload['shape'] == 'NOT_BOX' and payload['position'] not in {'UNCERTAIN', 'BREAKDOWN'}:
        raise GateError('negative shape has no box position')
    if payload['shape'] == 'BOX' and payload['subtype'] in {'MONOTONIC_TREND', 'PERSISTENT_BREAKDOWN', 'INSUFFICIENT_HISTORY'}:
        raise GateError('box subtype contradicts shape')
    if payload['shape'] == 'NOT_BOX' and payload['subtype'] == 'UNDECIDABLE':
        raise GateError('undecidable is not a negative subtype')
    reasons = payload['reasons']
    if not isinstance(reasons, list) or any(not isinstance(x, str) for x in reasons) or len(reasons) != len(set(reasons)) or not set(reasons) <= REASONS:
        raise GateError('invalid v1.1 reasons')
    if not isinstance(payload['note'], str) or len(payload['note']) > 300:
        raise GateError('invalid v1.1 note')
    start = payload['evidence_start']
    if start is not None and (type(start) is not int or not 0 <= start <= 41):
        raise GateError('evidence_start must be a daily bar ordinal 0..41')
    lower, upper = payload['lower_pct'], payload['upper_pct']
    if (lower is None) != (upper is None):
        raise GateError('both boundaries must be present or absent')
    if lower is not None:
        if payload['shape'] != 'BOX':
            raise GateError('only BOX may have boundary estimates')
        if any(type(v) not in (int, float) or not math.isfinite(v) or not -95 <= v <= 300 for v in (lower, upper)) or lower >= upper:
            raise GateError('invalid relative percentage boundaries')
    if type(payload['expected_revision']) is not int or payload['expected_revision'] < 0:
        raise GateError('invalid revision')
    return payload


class BoxStoreV11(BoxStore):
    """Reuse immutable task manifest; preserve v1 and smoke DBs untouched."""
    label_version = LABEL_VERSION
    annotation_prefix = 'annotations-v1.1'
    label_fields = ('shape', 'position', 'confidence', 'subtype', 'reasons',
                    'note', 'evidence_start', 'lower_pct', 'upper_pct')
    validator = staticmethod(validate)

    def task(self, tid, user):
        item = super().task(tid, user)
        row = self._task(tid)
        for scale, meta in row['scales'].items():
            raw = (self.root / 'raw' / meta['raw_file']).read_bytes()
            if digest(raw) != meta['raw_hash']:
                raise GateError('raw chart history drift')
            item['charts'][scale] = percent_axis(item['charts'][scale], raw)
        item['coordinate_contract'] = 'daily bars 0..41 oldest to T; boundary percent relative to T close'
        item['view_renderer_version'] = VIEW_RENDERER_VERSION
        return item

    def export_numeric(self, user, output):
        raise GateError('v1.1 export requires separately approved real-label training contract')

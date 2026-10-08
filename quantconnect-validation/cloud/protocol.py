"""Small derived-result protocol, shared verbatim by Cloud and local importer."""
import hashlib
import json
import re

PREFIX = 'SRQC1 '
MAX_OUTPUT_BYTES = 8000  # Reserve the remainder of Free's log for LEAN messages.
CLASSES = {'QC Confirms Out', 'QC Confirms In', 'QC Borderline',
           'QC Identity / Lifecycle Conflict', 'QC Coverage Unknown'}
FORBIDDEN = {'open', 'high', 'low', 'close', 'volume', 'dollarvolume',
             'ohlcv', 'bars', 'raw_market_data', 'history_rows'}


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=True, allow_nan=False)


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


def derived_only(value):
    if isinstance(value, dict):
        if FORBIDDEN.intersection(str(k).lower() for k in value):
            raise ValueError('QC raw market data cannot enter result protocol')
        for item in value.values():
            derived_only(item)
    elif isinstance(value, list):
        for item in value:
            derived_only(item)


def receipt_lines(run, records, status):
    derived_only(records)
    header = {'kind': 'begin', 'schema': 1, 'run': run['id'],
              'input_hash': run['input_hash'], 'code_hash': run['code_hash'],
              'layer': run['layer'], 'dates': run['dates']}
    body = [{'kind': 'row', 'seq': n, 'data': row} for n, row in enumerate(records)]
    end = {'kind': 'end', 'count': len(body), 'body_hash': digest(body),
           'status': status, 'truncated': False}
    lines = [PREFIX + canonical(row) for row in [header, *body, end]]
    if len(('\n'.join(lines) + '\n').encode()) > MAX_OUTPUT_BYTES:
        raise ValueError('Derived log too large; generate smaller predetermined chunk')
    return lines


def parse_receipt(text, run):
    rows = []
    for line in text.splitlines():
        # QC adds timestamp prefixes to downloaded logs.
        at = line.find(PREFIX)
        if at >= 0:
            rows.append(json.loads(line[at + len(PREFIX):]))
    if len(rows) < 2 or rows[0].get('kind') != 'begin' or rows[-1].get('kind') != 'end':
        raise ValueError('Missing begin/end: incomplete Cloud receipt')
    header, body, end = rows[0], rows[1:-1], rows[-1]
    for key, expected in [('schema', 1), ('run', run['id']),
                          ('input_hash', run['input_hash']), ('code_hash', run['code_hash']),
                          ('layer', run['layer']), ('dates', run['dates'])]:
        if header.get(key) != expected:
            raise ValueError('Frozen receipt mismatch: ' + key)
    if any(r.get('kind') != 'row' or r.get('seq') != n for n, r in enumerate(body)):
        raise ValueError('Duplicate, missing, or reordered receipt sequence')
    if end.get('count') != len(body) or end.get('body_hash') != digest(body):
        raise ValueError('Receipt content hash mismatch')
    if end.get('truncated') is not False or end.get('status') not in {'PASS', 'PARTIAL', 'FAIL'}:
        raise ValueError('Unknown/truncated Cloud result')
    normalized = '\n'.join(PREFIX + canonical(r) for r in rows) + '\n'
    if len(normalized.encode()) > MAX_OUTPUT_BYTES:
        raise ValueError('Cloud derived-output quota exceeded')
    records = [r['data'] for r in body]
    derived_only(records)
    dates = [r.get('date') for r in records if r.get('type') in {'membership', 'candidates'}]
    if run['layer'] in {'layer1', 'layer2'} and sorted(dates) != sorted(run['dates']):
        raise ValueError('Daily observations missing or duplicated')
    if run['layer'] == 'smoke':
        if len(records) != 1 or records[0].get('type') != 'smoke':
            raise ValueError('Smoke schema mismatch')
        required = {'history_access', 'stable_control', 'security_master', 'mapping', 'split_history'}
        checks = records[0].get('checks', {})
        if set(checks) != required or any(type(v) is not bool for v in checks.values()):
            raise ValueError('Smoke expected checks missing')
        if end['status'] == 'PASS' and not all(checks.values()):
            raise ValueError('False smoke PASS')
    return {'run': header['run'], 'layer': header['layer'], 'records': records,
            'input_hash': header['input_hash'], 'code_hash': header['code_hash'],
            'status': end['status'], 'receipt_hash': digest(rows)}


def normalize_cik(value):
    digits = str(value or '').strip()
    return digits.zfill(10) if digits.isdigit() and int(digits) else ''


def normalize_class(value):
    text = str(value or '').upper()
    match = re.search(r'\bCLASS[ -]+([A-Z0-9]+)\b', text)
    if match:
        return 'CLASS-' + match.group(1)
    if text.strip() in {'COMMON', 'ORDINARY'}:
        return text.strip()
    return ''


def historical_join(local, candidates, day):
    """A dated ticker locates candidates; issuer AND class or pinned SID verifies.

    Missing fields never become permission to merge/reuse identities. Generic
    common/ordinary descriptions cannot distinguish several issuer share classes.
    """
    mappings = [m for m in local.get('mappings', [])
                if m['from'] <= day <= (m.get('to') or '9999-12-31')]
    if len(mappings) != 1:
        return None, 'ambiguous_local_mapping'
    mapping = mappings[0]
    hits = [q for q in candidates if q['as_of'] == day and q['ticker'] == mapping['ticker']]
    if not hits:
        return None, 'qc_scope_or_data_missing'
    if len(hits) != 1:
        return None, 'ambiguous_qc_mapping'
    qc = hits[0]
    if qc.get('listing_date') and qc['listing_date'] > day:
        return None, 'future_qc_listing_conflict'
    pin = mapping.get('qc_sid')
    if pin and mapping.get('pin_available_on', '9999-12-31') <= day:
        return (qc, 'dated_sid_pin') if qc['sid'] == pin else (None, 'sid_conflict')
    observations = [o for o in local.get('issuers', []) if o['available_on'] <= day]
    ciks = {normalize_cik(o['cik']) for o in observations} - {''}
    if len(ciks) != 1 or not normalize_cik(qc.get('cik')):
        return None, 'issuer_evidence_missing'
    if normalize_cik(qc['cik']) not in ciks:
        return None, 'issuer_conflict'
    left, right = normalize_class(mapping.get('class')), normalize_class(qc.get('class'))
    if not left or not right or left != right:
        return None, 'class_evidence_missing_or_conflict'
    if left in {'COMMON', 'ORDINARY'} and sum(
            normalize_cik(q.get('cik')) in ciks for q in candidates) != 1:
        return None, 'multiple_issuer_share_classes'
    return qc, 'dated_issuer_class'


def membership_summary(local_count, qc_count, matched_local, matched_qc, unresolved):
    """Overlap bounds, with explicitly conditional set differences for unmatched IDs."""
    intersection = len(set(matched_local))
    union_upper = local_count + qc_count - intersection
    possible = intersection + min(unresolved, local_count - intersection, qc_count - intersection)
    union_lower = local_count + qc_count - possible
    return {'local_count': local_count, 'qc_count': qc_count, 'intersection': intersection,
            'local_only_upper': local_count - intersection, 'qc_only_upper': qc_count - intersection,
            'identity_unresolved': unresolved,
            'jaccard_lower': intersection / union_upper if union_upper else 1.,
            'jaccard_upper': possible / union_lower if union_lower else 1.,
            'top1000_overlap_lower': intersection / local_count if local_count else None,
            'definitive': unresolved == 0, 'matched_qc_count': len(set(matched_qc))}

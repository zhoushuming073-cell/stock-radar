"""Explicit official-fact rules. No LLM prose can certify or rewrite a master."""
from urllib.parse import urlparse
from pathlib import Path
import hashlib
import html
import json
import re
from datetime import datetime, time
from zoneinfo import ZoneInfo

REQUIRED = {'local_uid', 'date', 'local_interpretation', 'qc_interpretation', 'official_evidence',
            'issuer_cik', 'share_class', 'ticker_history', 'exchange', 'material_action',
            'confidence', 'changes_core', 'changes_candidate', 'changes_trade', 'use'}


def validate_case(case):
    if not REQUIRED.issubset(case):
        raise ValueError('Missing machine-readable evidence fields')
    if case['use'] not in {'asof_decision', 'retrospective_validation'}:
        raise ValueError('Evidence timing semantics missing')
    valid = []
    for fact in case['official_evidence']:
        required = {'url', 'publisher_type', 'source_date', 'published_at', 'captured_sha256',
                    'issuer_cik', 'share_class', 'assertion', 'supports_qc_sid'}
        if not required.issubset(fact):
            raise ValueError('Official fact lacks provenance')
        host = (urlparse(fact['url']).hostname or '').lower()
        publisher = fact['publisher_type']
        trusted = (publisher == 'SEC' and (host == 'sec.gov' or host.endswith('.sec.gov')) or
                   publisher == 'exchange' and any(host == d or host.endswith('.' + d) for d in ['nasdaq.com', 'nyse.com']) or
                   publisher == 'FINRA' and (host == 'finra.org' or host.endswith('.finra.org')) or
                   publisher == 'issuer' and fact.get('issuer_domain_verified') is True)
        stamp = datetime.fromisoformat(fact['published_at'].replace('Z', '+00:00'))
        cutoff = datetime.combine(datetime.fromisoformat(case['date']).date(), time(16), ZoneInfo('America/New_York'))
        timing = (case['use'] == 'retrospective_validation' or
                  (stamp <= cutoff if stamp.tzinfo else stamp.date() < cutoff.date()))
        same_identity = fact['issuer_cik'] == case['issuer_cik'] and fact['share_class'] == case['share_class']
        primary_content_verified = False
        if fact.get('payload_path') and fact.get('http_receipt_path') and fact.get('primary_excerpt'):
            payload_path, receipt_path = Path(fact['payload_path']), Path(fact['http_receipt_path'])
            if payload_path.is_file() and receipt_path.is_file():
                raw = payload_path.read_bytes()
                receipt = json.loads(receipt_path.read_text(encoding='utf-8'))
                normalized = re.sub(r'\s+', ' ', html.unescape(re.sub('<[^>]+>', ' ', raw.decode('utf-8', errors='replace'))))
                excerpt = re.sub(r'\s+', ' ', fact['primary_excerpt'])
                primary_content_verified = (hashlib.sha256(raw).hexdigest() == fact['captured_sha256'] and
                    receipt.get('status') == 200 and receipt.get('url') == fact['url'] and
                    receipt.get('sha256') == fact['captured_sha256'] and len(excerpt) >= 40 and excerpt in normalized and
                    str(int(case['issuer_cik'])) in normalized and case['share_class'].replace('-', ' ').lower() in normalized.lower())
        if trusted and timing and same_identity and primary_content_verified:
            valid.append(fact)
    sids = {f['supports_qc_sid'] for f in valid if f['supports_qc_sid']}
    qc_verified = False
    qc = case.get('qc_interpretation') or {}
    if qc.get('receipt_path') and qc.get('receipt_sha256') and Path(qc['receipt_path']).is_file():
        path = Path(qc['receipt_path']); receipt = json.loads(path.read_text(encoding='utf-8'))
        if (hashlib.sha256(path.read_bytes()).hexdigest() == qc['receipt_sha256'] and
                receipt.get('origin') == 'quantconnect_cloud_download' and receipt.get('receipt_verified') is True):
            for record in receipt.get('records', []):
                if record.get('date') != case['date']:
                    continue
                for conflict in record.get('local_conflicts', []):
                    for candidate in conflict.get('qc_identity_candidates', []):
                        if (candidate['sid'] in sids and candidate['cik'] == case['issuer_cik'] and
                                candidate['class'] == case['share_class'] and candidate['as_of'] == case['date']):
                            qc_verified = True
    # Dated evidence may establish an identity bridge, never blanket data/portfolio PASS.
    passed = len(valid) >= 2 and len({f['url'] for f in valid}) >= 2 and len(sids) == 1 and qc_verified
    return {'evidence_status': 'PASS' if passed else 'FAIL',
            'classification': 'VERIFIED_SCOPED_IDENTITY' if passed else 'UNRESOLVED',
            'qc_sid': next(iter(sids)) if passed else None,
            'master_modified': False, 'pit_release_pass': False,
            'asof_selection_usable': passed and case['use'] == 'asof_decision'}

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

"""QC-only data access. Local membership/identity never constructs QC Core."""
from AlgorithmImports import *
from datetime import datetime, timedelta
import pandas as pd


def historical_population(algorithm, universe, day):
    start = datetime.fromisoformat(day)
    # Fundamental objects at the historical timestamp: do not call current Fundamentals().
    series = algorithm.history(universe, start, start + timedelta(days=1))
    objects = []
    for key, group in series.items():
        stamp = key[-1] if isinstance(key, tuple) else key
        if str(pd.Timestamp(stamp).date()) != day:
            raise ValueError('Unexpected fundamental timestamp; no date backfill')
        objects.extend(group)
    if not objects:
        raise ValueError('Historical universe inaccessible; never substitute current symbols')
    seen, result = set(), []
    for f in objects:
        sid = str(f.symbol.id)
        if sid in seen:
            raise ValueError('Duplicate historical SID')
        seen.add(sid)
        ref = f.security_reference
        kind = str(ref.security_type)
        ipo = ref.ipo_date
        listing = str(ipo.date()) if ipo.year > 1900 else None
        result.append({'symbol_object': f.symbol, 'sid': sid, 'ticker': f.symbol.value,
            'as_of': day, 'cik': normalize_cik(f.company_reference.cik),
            'class': normalize_class(ref.share_class_description),
            'security_type': 'common' if kind == 'ST00000001' and not ref.is_depositary_receipt
                             else ('unknown' if not kind else 'other'),
            'listing_date': listing})
    return result


def raw_frames(algorithm, symbols, first, end):
    """Typed history retains immutable Symbol.ID; no DataFrame ticker-string join."""
    frames = {str(s.id): [] for s in symbols}
    for offset in range(0, len(symbols), 128):
        batch = symbols[offset:offset + 128]
        history = algorithm.history[TradeBar](batch, datetime.fromisoformat(first), end,
            Resolution.DAILY, fill_forward=False, data_normalization_mode=DataNormalizationMode.RAW)
        for sliced in history:
            for symbol in batch:
                if not sliced.contains_key(symbol):
                    continue
                bar = sliced[symbol]
                sid = str(symbol.id)
                if sid not in frames or bar.is_fill_forward:
                    raise ValueError('Foreign SID/fill-forward in raw history')
                # daily_precise_end_time: bar closes on its actual session date.
                date = str(bar.end_time.date())
                if bar.end_time.hour not in {13, 16} or bar.end_time > end:
                    raise ValueError('Raw daily timestamp semantics failed; run smoke first')
                frames[sid].append({'date': date, 'open': float(bar.open), 'high': float(bar.high),
                    'low': float(bar.low), 'close': float(bar.close), 'volume': float(bar.volume)})
    for sid, rows in frames.items():
        frame = pd.DataFrame(rows, columns=['date', 'open', 'high', 'low', 'close', 'volume'])
        if frame.date.duplicated().any():
            raise ValueError('Duplicate raw daily sessions')
        frame['date'] = pd.to_datetime(frame.date)
        frames[sid] = frame.set_index('date').sort_index()
    return frames


def split_actions(algorithm, symbol, first, end):
    result = []
    for event in algorithm.history[Split](symbol, datetime.fromisoformat(first), end):
        if event.type != SplitType.SPLIT_OCCURRED:
            continue
        if event.end_time > end or float(event.split_factor) <= 0:
            raise ValueError('Invalid/future split event')
        result.append({'security_id': str(symbol.id), 'effective_date': str(event.end_time.date()),
            'event_type': 'split', 'confidence': 'verified', 'handling_mode': 'native_raw_split',
            'ratio': 1 / float(event.split_factor)})
    return result

RUN = {'id': 'smoke-split', 'layer': 'smoke', 'case': 'NVDA', 'dates': ['2024-06-06', '2024-06-12'], 'input_hash': '385eae113ab2bab022d9e95adbf3ce28a4cacd7c6047b30bca7711c2615e7812', 'code_hash': 'ef71466df2646dbe5ed1b56a6cce3d5381909dcf16b4ee6e60922f557efdbdb4'}
from AlgorithmImports import *
from datetime import datetime, timedelta

# The generator inlines protocol.py and a frozen RUN before this class.
class StockRadarCloudSmoke(QCAlgorithm):
    def initialize(self):
        self.set_name('SRQC-' + RUN['id'])
        first, last = (datetime.fromisoformat(d) for d in RUN['dates'])
        self.set_start_date(first.year, first.month, first.day)
        self.set_end_date(last.year, last.month, last.day)
        self.set_time_zone(TimeZones.NEW_YORK)
        self.settings.daily_precise_end_time = True
        self.set_cash(1000000)
        self.universe_settings.resolution = Resolution.DAILY
        self._universe = self.add_universe(lambda _: Universe.UNCHANGED)
        tickers = ['SPY', 'MSFT', RUN['case']]
        self._symbols = {}
        for ticker in tickers:
            # String subscriptions resolve today's reused ticker, not the historical issuer.
            sid = SecurityIdentifier.generate_equity(ticker, Market.USA, mapping_resolve_date=first)
            symbol = Symbol(sid, ticker)
            self._symbols[ticker] = self.add_security(symbol, Resolution.DAILY, fill_forward=False,
                data_normalization_mode=DataNormalizationMode.RAW).symbol
        self._seen = {str(s.id): set() for s in self._symbols.values()}
        self._mapping = []
        self._splits = []

    def on_data(self, data):
        for symbol in self._symbols.values():
            if not data.bars.contains_key(symbol):
                continue
            bar = data.bars[symbol]
            sid = str(symbol.id)
            if sid in self._seen and not bar.is_fill_forward and bar.close > 0:
                self._seen[sid].add(str(bar.end_time.date()))

    def on_symbol_changed_events(self, events):
        for event in events.values():
            self._mapping.append([str(event.symbol.id), event.old_symbol, event.new_symbol,
                                  self.time.strftime('%Y-%m-%d')])

    def on_splits(self, splits):
        for split in splits.values():
            if split.type == SplitType.SPLIT_OCCURRED:
                self._splits.append([str(split.symbol.id), self.time.strftime('%Y-%m-%d'),
                                     float(split.split_factor)])

    def on_end_of_algorithm(self):
        case = self._symbols[RUN['case']]
        master_ok, split_history_ok, history_ok = False, False, False
        try:
            frames = raw_frames(self, [case, self._symbols['MSFT']], RUN['dates'][0], self.time)
            history_ok = all(len(frame) >= 3 for frame in frames.values())
            universe_history = self.history(self._universe, 1, Resolution.DAILY)
            for _, fundamentals in universe_history.items():
                for f in fundamentals:
                    if f.symbol.id == case.id:
                        master_ok = (bool(normalize_cik(f.company_reference.cik)) and
                                     str(f.security_reference.security_type) == 'ST00000001')
            splits = list(self.history[Split](case, datetime.fromisoformat(RUN['dates'][0]), self.time))
            split_history_ok = (RUN['case'] == 'FB' or any(
                s.type == SplitType.SPLIT_OCCURRED and abs(float(s.split_factor) - .1) < 1e-10
                for s in splits))
        except Exception as error:
            # Error type only: never print dataset rows or credential-bearing exceptions.
            self._api_error = type(error).__name__
        mapping_ok = (RUN['case'] != 'FB' or any(
            e[0] == str(case.id) and e[1] == 'FB' and e[2] == 'META' and e[3] == '2022-06-09'
            for e in self._mapping))
        split_ok = (RUN['case'] != 'NVDA' or any(
            e[0] == str(case.id) and e[1] == '2024-06-10' and abs(e[2] - .1) < 1e-10
            for e in self._splits))
        checks = {'history_access': history_ok,
                  'stable_control': all(len(v) >= 3 for v in self._seen.values()),
                  'security_master': master_ok, 'mapping': mapping_ok,
                  'split_history': split_ok and split_history_ok}
        record = {'type': 'smoke', 'checks': checks, 'case': RUN['case'],
                  'sid': str(case.id), 'observed_sessions': sorted(self._seen[str(case.id)]),
                  'mapping_events': self._mapping, 'split_events': self._splits,
                  'api_error_type': getattr(self, '_api_error', None)}
        status = 'PASS' if all(checks.values()) else 'FAIL'
        for line in receipt_lines(RUN, [record], status):
            self.log(line)
        # Cloud Debug is capped at 200 characters; keep full receipts in Log.
        self.debug('SRQC_SMOKE ' + canonical({'case': RUN['case'], 'checks': checks, 'status': status}))

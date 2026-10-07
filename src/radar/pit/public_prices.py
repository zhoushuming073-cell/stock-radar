"""Explicit public-source acquisition; immutable SQL snapshots, never live ticker joins.

The DoltHub LICENSE.md declares CC BY-SA 4.0. Preserve attribution and license
when redistributing derived data. No network is performed during module import.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import urllib.parse
import urllib.request
import urllib.error

PROVIDER = "post-no-preference/stocks"
LICENSE = "CC-BY-SA-4.0"
API = "https://www.dolthub.com/api/v1alpha1/post-no-preference/stocks/master"


def capture(url: str, cache: Path, *, attempts: int = 3) -> dict:
    """Content address raw bytes; receipt times are outside semantic content hashes."""
    cache.mkdir(parents=True, exist_ok=True)
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(url, headers={"User-Agent":
                "StockRadarPIT research https://github.com/zhoushuming073-cell/stock-radar"})
            with urllib.request.urlopen(request, timeout=30) as response:
                raw, final_url = response.read(), response.url
            sha = hashlib.sha256(raw).hexdigest()
            target = cache / (sha + ".raw")
            if target.exists() and target.read_bytes() != raw:
                raise ValueError("raw cache collision")
            if not target.exists():
                target.write_bytes(raw)
            receipt = {"url": url, "final_url": final_url, "raw_sha256": sha,
                       "bytes": len(raw), "captured_at": datetime.now(timezone.utc).isoformat()}
            receipt_file = cache / (sha + ".receipt.json")
            if not receipt_file.exists():
                receipt_file.write_text(json.dumps(receipt, indent=2), encoding="utf-8")
            return receipt
        except urllib.error.HTTPError as error:
            if error.code not in {408, 429, 500, 502, 503, 504} or attempt == attempts - 1:
                raise
            try:
                delay = float(error.headers.get('Retry-After', 1 + attempt))
            except (TypeError, ValueError):
                delay = 1 + attempt
            time.sleep(min(max(delay, 1), 30))
        except (OSError, TimeoutError):
            if attempt == attempts - 1:
                raise
            time.sleep(1 + attempt)
    raise RuntimeError("unreachable")


def query(sql: str, cache: Path) -> tuple[list[dict], dict]:
    cache.mkdir(parents=True, exist_ok=True)
    index = cache / ("query-" + hashlib.sha256(sql.encode()).hexdigest() + ".json")
    if index.exists():
        saved = json.loads(index.read_text(encoding="utf-8"))
        raw = (cache / (saved["raw_sha256"] + ".raw")).read_bytes()
        if hashlib.sha256(raw).hexdigest() != saved["raw_sha256"]:
            raise ValueError("cached query raw hash mismatch")
        payload = json.loads(raw)
        if payload.get("sql_query") != sql or payload.get("query_execution_status") != "Success":
            raise ValueError("cached SQL failed/truncated/mismatched")
        return payload["rows"], saved
    receipt = capture(API + "?" + urllib.parse.urlencode({"q": sql}), cache)
    try:
        payload = json.loads((cache / (receipt["raw_sha256"] + ".raw")).read_text(encoding="utf-8"))
    except (ValueError, UnicodeError):
        quarantine = cache / 'quarantine'
        quarantine.mkdir(exist_ok=True)
        (quarantine / (receipt['raw_sha256'] + '.decision.json')).write_text(json.dumps({
            'receipt':receipt, 'status':'rejected_invalid_json','sql':sql},indent=2),encoding='utf-8')
        raise ValueError('public SQL payload is not valid JSON')
    # RowLimit means truncated data, even though HTTP status is 200.
    if payload.get("query_execution_status") != "Success":
        quarantine = cache / 'quarantine'
        quarantine.mkdir(exist_ok=True)
        (quarantine / (receipt['raw_sha256'] + '.decision.json')).write_text(json.dumps({
            'receipt':receipt,'status':'rejected_failed_or_truncated','sql':sql},indent=2),encoding='utf-8')
        raise ValueError("public SQL failed/truncated: " + payload.get("query_execution_message", ""))
    if payload.get("sql_query") != sql:
        raise ValueError("source SQL receipt mismatch")
    saved = {**receipt, "sql": sql}
    index.write_text(json.dumps(saved, indent=2), encoding="utf-8")
    return payload["rows"], saved


def acquire_symbol(symbol: str, pin: str, start: str, end: str, cache: Path) -> dict:
    """Bound date scans to small chunks: the table's primary key starts with date.

    AS OF fixes data; point date lists avoid slow range scans in the public API.
    Replay uses hashed raw bytes. Ticker queries require identity review.
    """
    from datetime import date, timedelta
    if not re.fullmatch(r"[A-Z0-9.-]{1,20}", symbol) or not re.fullmatch(r"[0-9a-v]{32}", pin):
        raise ValueError("invalid symbol or Dolt commit")
    first, last = date.fromisoformat(start), date.fromisoformat(end)
    if first > last:
        raise ValueError("reversed price acquisition interval")
    rows, receipts = [], []
    cursor = first
    while cursor <= last:
        through = min(last, cursor + timedelta(days=30))
        dates = ",".join("'" + str(cursor + timedelta(days=n)) + "'" for n in range((through-cursor).days + 1))
        sql = (f"SELECT * FROM ohlcv AS OF '{pin}' WHERE date IN ({dates}) "
               f"AND act_symbol='{symbol}' ORDER BY date LIMIT 100")
        chunk, receipt = query(sql, cache)
        if len(chunk) >= 100:
            raise ValueError("price chunk may be truncated")
        rows.extend(chunk)
        receipts.append(receipt)
        cursor = through + timedelta(days=1)
    ancillary = {}
    for table in ("split", "dividend", "symbol"):
        sql = f"SELECT * FROM {table} AS OF '{pin}' WHERE act_symbol='{symbol}'"
        ancillary[table], receipt = query(sql, cache)
        receipts.append(receipt)
    payload = {"provider": PROVIDER, "license": LICENSE, "source_version": pin,
               "source_symbol": symbol, "requested_start": start, "requested_end": end,
               "rows": rows, "ancillary": ancillary,
               "queries": [{k: r[k] for k in ("url", "raw_sha256", "sql")} for r in receipts],
               "adjustment": "unverified", "session_date": "US exchange session label",
               "version_check": "SQL AS OF immutable commit; offline replay from hashed raw bytes",
               "status": "quarantined_requires_identity_and_adjustment_review"}
    sha = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    (cache / (symbol + "-" + sha + ".json")).write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return {"symbol": symbol, "sha256": sha, "rows": len(rows), "file": str(cache / (symbol + "-" + sha + ".json"))}


def acquire_sessions(symbol: str, pin: str, sessions: list[str], cache: Path) -> dict:
    """Fetch only the missing exchange labels; empty gaps perform no network IO."""
    from datetime import date
    if not re.fullmatch(r"[A-Z0-9.-]{1,20}", symbol) or not re.fullmatch(r"[0-9a-v]{32}", pin):
        raise ValueError("invalid symbol or Dolt commit")
    if sessions != sorted(set(sessions)) or any(str(date.fromisoformat(d)) != d for d in sessions):
        raise ValueError("missing sessions must be unique ordered ISO dates")
    if not sessions:
        return {"symbol": symbol, "rows": 0, "status": "price_scope_complete_no_fetch"}
    rows, receipts, ancillary = [], [], {}
    for offset in range(0, len(sessions), 30):
        dates = ','.join("'"+d+"'" for d in sessions[offset:offset+30])
        sql = (f"SELECT * FROM ohlcv AS OF '{pin}' WHERE date IN ({dates}) "
               f"AND act_symbol='{symbol}' ORDER BY date LIMIT 100")
        chunk, receipt = query(sql, cache)
        if len(chunk) >= 100:
            raise ValueError('price chunk may be truncated')
        rows.extend(chunk); receipts.append(receipt)
    for table in ('split', 'dividend', 'symbol'):
        ancillary[table], receipt = query(f"SELECT * FROM {table} AS OF '{pin}' WHERE act_symbol='{symbol}'", cache)
        receipts.append(receipt)
    payload = {'provider':PROVIDER, 'license':LICENSE, 'source_version':pin,
        'source_symbol':symbol, 'requested_start':sessions[0], 'requested_end':sessions[-1],
        'requested_sessions':sessions, 'rows':rows, 'ancillary':ancillary,
        'queries':[{k:r[k] for k in ('url','raw_sha256','sql')} for r in receipts],
        'adjustment':'unverified', 'session_date':'US exchange session label',
        'status':'quarantined_requires_identity_and_adjustment_review'}
    sha=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
    artifact=cache/(symbol+'-'+sha+'.json')
    artifact.write_text(json.dumps(payload,indent=2),encoding='utf-8')
    return {'symbol':symbol,'sha256':sha,'rows':len(rows),'file':str(artifact)}

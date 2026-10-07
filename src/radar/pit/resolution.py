"""Resumable evidence/price resolution queue. Acceptance never upgrades a name match.

Workers write new local evidence/price artifacts, not the installed master or old
databases. A historical identity review remains mandatory for new mappings.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sqlite3
import time
import uuid

from radar.pit.builder import digest
from radar.pit.features import file_hash
from radar.pit.trust import load_catalog


class ResolutionQueue:
    def __init__(self, path: Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as c:
            c.execute("""CREATE TABLE IF NOT EXISTS tasks (
                task_id TEXT PRIMARY KEY, security_id TEXT NOT NULL, priority INTEGER NOT NULL,
                payload TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending', attempts INTEGER NOT NULL DEFAULT 0,
                lease_until TEXT, lease_token TEXT, outcome TEXT, updated_at TEXT NOT NULL)""")
            c.execute('''CREATE TABLE IF NOT EXISTS task_attempt_event (
                seq INTEGER PRIMARY KEY, task_id TEXT, lease_token TEXT, outcome TEXT, outcome_sha256 TEXT, recorded_at TEXT)''')

    def connect(self):
        c = sqlite3.connect(self.path, timeout=30)
        c.row_factory = sqlite3.Row
        return c

    def seed(self, manifest: dict, near_ids: set[str] | None = None):
        """Idempotent P0 first; P1 selected/near-threshold; unpriced members retained."""
        selected = {s["security_id"] for s in manifest["signals"]}
        near_ids = near_ids or set()
        with self.connect() as c:
            for row in manifest["dependencies"]:
                unresolved = (row["missing_sessions"] or not row["certificate"].get("verified")
                              or not all(m.get("resolution_status") == "verified" for m in row["mappings"])
                              or any(a["handling_mode"] == "blocked" for a in row["actions"]))
                priority = 0 if unresolved else 1 if row["security_id"] in selected | near_ids else 2
                payload = {"dependency_sha256": manifest["dependency_sha256"], "dependency": row,
                           "selected": row["security_id"] in selected,
                           "near_threshold": row["security_id"] in near_ids}
                key = digest(payload)
                c.execute("""INSERT OR IGNORE INTO tasks(task_id,security_id,priority,payload,updated_at)
                    VALUES(?,?,?,?,?)""", [key, row["security_id"], priority, json.dumps(payload), self.now()])

    @staticmethod
    def now():
        return datetime.now(timezone.utc).isoformat()

    def claim(self) -> dict | None:
        """Atomic lease; crashed workers can resume without duplicating accepted files."""
        with self.connect() as c:
            c.execute("BEGIN IMMEDIATE")
            row = c.execute("""SELECT * FROM tasks WHERE status='pending' OR
                (status='running' AND lease_until<?) ORDER BY priority,
                json_extract(payload,'$.selected') DESC, json_extract(payload,'$.near_threshold') DESC,
                security_id,task_id LIMIT 1""", [self.now()]).fetchone()
            if row is None:
                return None
            token = str(uuid.uuid4())
            c.execute("""UPDATE tasks SET status='running', attempts=attempts+1,lease_until=?,
                lease_token=?,updated_at=? WHERE task_id=?""",
                [(datetime.now(timezone.utc) + timedelta(minutes=15)).isoformat(), token, self.now(), row["task_id"]])
            return {**dict(row), "lease_token": token, "payload": json.loads(row["payload"])}

    def finish(self, task: dict, outcome: dict):
        if outcome["status"] not in {"accepted", "quarantined", "blocked", "failed"}:
            raise ValueError("invalid resolution decision")
        with self.connect() as c:
            changed = c.execute("""UPDATE tasks SET status=?,outcome=?,lease_until=NULL,updated_at=?
                WHERE task_id=? AND status='running' AND lease_token=?""",
                [outcome["status"], json.dumps(outcome), self.now(), task["task_id"], task["lease_token"]]).rowcount
            if changed != 1:
                raise ValueError("resolution lease lost")
            c.execute('INSERT INTO task_attempt_event(task_id,lease_token,outcome,outcome_sha256,recorded_at) VALUES (?,?,?,?,?)',
                      [task['task_id'],task['lease_token'],json.dumps(outcome),digest(outcome),self.now()])

    def retry_failed(self, max_attempts: int = 3):
        if not 1 <= max_attempts <= 10:
            raise ValueError('invalid resolution retry limit')
        with self.connect() as c:
            return c.execute("UPDATE tasks SET status='pending',lease_until=NULL WHERE status='failed' AND attempts<?",
                             [max_attempts]).rowcount

    def summary(self):
        with self.connect() as c:
            return [dict(r) for r in c.execute("SELECT priority,status,COUNT(*) count FROM tasks GROUP BY priority,status ORDER BY priority,status")]


def official_candidates(root: Path) -> dict:
    """Cache official current metadata for discovery; never historical certification."""
    from radar.pit.public_prices import capture
    raw = Path(root) / 'data/pit/raw/resolution'
    index = raw / 'sec-current-discovery.json'
    if index.exists():
        receipt = json.loads(index.read_text(encoding='utf-8'))
        path = raw / (receipt['raw_sha256'] + '.raw')
        if file_hash(path) != receipt['raw_sha256']:
            raise ValueError('official discovery raw hash changed')
    else:
        receipt = capture('https://www.sec.gov/files/company_tickers_exchange.json', raw, attempts=2)
        index.write_text(json.dumps(receipt, indent=2), encoding='utf-8')
    response = json.loads((raw / (receipt['raw_sha256'] + '.raw')).read_text(encoding='utf-8'))
    if set(response.get('fields', [])) != {'cik', 'name', 'ticker', 'exchange'}:
        raise ValueError('SEC discovery response schema is not the expected metadata table')
    result = {}
    for values in response['data']:
        item = dict(zip(response['fields'], values))
        result.setdefault(item['ticker'], []).append({**item, 'source':receipt,
            'decision':'quarantined_current_metadata_only; historical class/listing/reuse require official filing review'})
    return result


def resolve_task(root: Path, task: dict, *, network: bool = False, pin: str | None = None,
                 catalog: dict | None = None, discovery: dict | None = None) -> dict:
    """Existing official evidence → candidate public filings → scoped price fetch.

    SEC metadata describes current issuers, not historical security membership.
    Unresolved securities remain blocked; filings and prices go to quarantine.
    """
    root = Path(root)
    row = task["payload"]["dependency"]
    catalog = catalog or load_catalog(root / "config/pit_trust_evidence.json", root / "data/pit/raw/official-evidence")
    local = [m for m in catalog["mappings"] if m["security_id"] == row["security_id"]
             and m["confidence"] == "verified"]
    sources = sorted({m["source"] for m in local})
    outcome = {"status": "blocked", "security_id": row["security_id"], "local_evidence": sources,
               "identity_merged": False, "installed_artifacts_modified": False, "artifacts": [], "reasons": []}
    if not local:
        outcome['official_metadata_candidates'] = [candidate for symbol in row['symbols']
                                                   for candidate in (discovery or {}).get(symbol, [])]
        if outcome['official_metadata_candidates']:
            outcome['status'] = 'quarantined'
        outcome["reasons"].append("no scoped official issuer/class/exchange identity; names/current ticker metadata cannot resolve historical reuse")
        return outcome
    # Require master agreement rather than inventing missing official intervals.
    verified = all(m.get("resolution_status") == "verified" for m in row["mappings"])
    if not verified:
        outcome["reasons"].append("official identity scope does not cover this episode; review required")
        return outcome
    reviewed = root / 'data/pit/resolution-reviews' / (digest(row['security_id']) + '.json')
    if reviewed.exists():
        from radar.lab.universe import LocalSecurityMaster
        from radar.pit.price_import import accept_prices
        decision = json.loads(reviewed.read_text(encoding='utf-8'))
        if decision.get('dependency_sha256') != task['payload']['dependency_sha256']:
            raise ValueError('resolution review is bound to another run dependency')
        price_review = decision['price_review']
        if {s['security_id'] for s in price_review['series']} != {row['security_id']}:
            raise ValueError('resolution review cannot accept unrelated identities')
        required = set(row['required_sessions'])
        if set(price_review['sessions']) != required:
            raise ValueError('resolution acceptance must cover the exact frozen required sessions')
        master = LocalSecurityMaster(root/'data/security-master.csv',root/'data/security-master-manifest.json')
        raw = Path(decision['raw_directory'])
        raw = raw if raw.is_absolute() else root/raw
        key = digest({'review':decision,'master_fingerprint':master.fingerprint})
        destination = root/'data/pit/accepted'/key/'external-prices.duckdb'
        if destination.exists():
            receipt = json.loads(destination.with_suffix('.manifest.json').read_text(encoding='utf-8'))
            if file_hash(destination) != receipt['database_sha256']:
                raise ValueError('accepted resolution artifact changed')
            replay = accept_prices(raw,price_review,master,destination,raw_actions=decision.get('raw_actions'),validate_only=True)
            if any(replay[key] != receipt[key] for key in ('review_sha256','rows_sha256','rows')):
                raise ValueError('accepted resolution evidence differs on replay')
        else:
            receipt = accept_prices(raw,price_review,master,destination,raw_actions=decision.get('raw_actions'))
        outcome.update({'status':'accepted','artifacts':[receipt],
                        'reasons':['reviewed exact run scope accepted into a new store; installation/features/run certification remain separate']})
        return outcome
    if not network:
        outcome["reasons"].append("existing evidence reused; price/action acceptance requires explicit complete raw/basis/license review")
        return outcome
    from radar.pit.public_prices import acquire_symbol
    raw = root / "data/pit/raw/resolution"
    for mapping in local:
        first = max(min(row["required_sessions"]), mapping["valid_from"])
        last = min(max(row["required_sessions"]), mapping["valid_to"])
        if first > last:
            continue
        acquisition = acquire_symbol(mapping["symbol"], pin, first, last, raw)
        artifact = Path(acquisition["file"])
        outcome["artifacts"].append({**acquisition, "physical_sha256": file_hash(artifact)})
    outcome["status"] = "quarantined"
    outcome["reasons"].append("downloaded immutable OHLCV/split/dividend/symbol data; raw identity/basis/license/calendar acceptance not inferred from HTTP success")
    return outcome


def work(root: Path, queue: ResolutionQueue, *, limit: int = 20, network: bool = False,
         pin: str | None = None, pause_seconds: float = 1.0):
    if not 0 <= limit <= 1000 or pause_seconds < 0:
        raise ValueError("invalid resolution worker bounds")
    outcomes = []
    catalog = load_catalog(Path(root) / 'config/pit_trust_evidence.json', Path(root) / 'data/pit/raw/official-evidence')
    discovery = {}
    if network:
        try:
            discovery = official_candidates(root)
        except (ValueError, OSError, TimeoutError) as error:
            outcomes.append({'status':'failed', 'stage':'official_discovery', 'reason':str(error),
                             'policy':'access denial is not bypassed; continue existing scoped evidence'})
    for _ in range(limit):
        task = queue.claim()
        if task is None:
            break
        try:
            result = resolve_task(root, task, network=network, pin=pin,catalog=catalog,discovery=discovery)
        except (ValueError, OSError, TimeoutError) as error:
            result = {"status": "failed", "security_id": task["security_id"], "reason": str(error)}
        queue.finish(task, result)
        outcomes.append(result)
        if network:
            time.sleep(pause_seconds)
    return outcomes

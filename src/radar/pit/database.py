"""Reusable historical database contracts, separate from strategy readiness.

The population is the observed candidate census, not an attested whole-market
census. Full-window identity ratings must never filter a past population.
"""
from __future__ import annotations

from datetime import date
from functools import lru_cache
import hashlib
import json
from pathlib import Path
import shutil

import duckdb
import numpy as np
import pandas as pd

from radar.pit.features import file_hash
from radar.pit.research import _name, _same_name

MEMBER_STATES = {"confirmed_member", "probable_member", "unknown", "confirmed_non_member"}
LIFECYCLE_TYPES = {
    "listing", "split", "reverse_split", "ticker_change", "exchange_transfer",
    "merger", "acquisition", "cash_acquisition", "stock_conversion", "bankruptcy",
    "delisting", "otc_continuation", "termination", "trading_suspension",
    "equity_cancellation", "liquidation", "observation_end", "new_observation",
    "class_transition", "name_change",
}


def membership_truth(status: str):
    """Probable is positive evidence, not certainty; unknown stays nullable."""
    if status not in MEMBER_STATES:
        raise ValueError("unknown membership state")
    return None if status == "unknown" else status != "confirmed_non_member"


def fixed_sample(ids, count: int, seed: str):
    return sorted(set(ids), key=lambda s: (hashlib.sha256((seed + "|" + s).encode()).hexdigest(), s))[:count]


@lru_cache(maxsize=150000)
def compatible_name(a, b):
    return bool(_name(a) and _name(b) and _same_name(_name(a), _name(b)))


def validate_intervals(frame):
    """Different symbols or types cannot overlap for one internal identity."""
    required = {"security_id", "symbol", "valid_from", "valid_to", "security_type"}
    if not required <= set(frame):
        raise ValueError("incomplete historical interval schema")
    f = frame.copy()
    for col in ("valid_from", "valid_to"):
        f[col] = pd.to_datetime(f[col], errors="raise")
    if f[list(required)].isna().any().any() or f.valid_from.gt(f.valid_to).any():
        raise ValueError("invalid interval dates/identity")
    for key in ("symbol", "security_id"):
        ordered = f.sort_values([key, "valid_from", "valid_to"])
        previous = ordered.groupby(key).valid_to.shift()
        if ordered.valid_from.le(previous).any():
            raise ValueError("overlapping " + key + " episodes")


def validate_prices(frame):
    required = {"security_id", "symbol", "date", "open", "high", "low", "close", "volume",
                "source", "source_version", "retrieved_at", "basis", "action_relation", "conflict_state"}
    if not required <= set(frame) or frame[list(required)].isna().any().any():
        raise ValueError("incomplete price provenance")
    if frame.duplicated(["security_id", "date", "basis"]).any():
        raise ValueError("duplicate accepted price")
    if frame.groupby("security_id").basis.nunique().gt(1).any():
        raise ValueError("mixed adjustment basis within an accepted series")
    if (~frame.basis.isin(["raw", "split", "all"])).any():
        raise ValueError("unknown adjustment basis")
    if (frame[list(required)].astype(str).eq("").any().any()
            or not np.isfinite(frame[['open','high','low','close','volume']].astype(float)).all().all()
            or frame.low.le(0).any() or frame.volume.lt(0).any()
            or frame.volume.ne(np.floor(frame.volume)).any()
            or not frame.open.between(frame.low, frame.high).all()
            or not frame.close.between(frame.low, frame.high).all()):
        raise ValueError("invalid price/provenance")


def classify_episode(record, rules):
    """Deterministic audit classification. Never merges internal identities."""
    high = []
    medium = []
    if record["cik_count"] > 1:
        high.append("multiple_cik")
    if record["ticker_episode_count"] > 1:
        high.append("ticker_reuse_or_unresolved_fragmentation")
    if record["type_count"] > 1:
        high.append("security_class_transition")
    if record["material_unresolved"]:
        high.append("material_event_unresolved")
    if record["disappeared"] and not record["official_terminal"]:
        high.append("unexplained_observation_end")
    if record["security_type"] != "common":
        high.append("outside_common_scope_or_class_ambiguity")
    if record["price_anomaly"]:
        medium.append("price_continuity_review")
    if record["price_conflict"]:
        medium.append("source_price_conflict")
    if record["cik_count"] != 1 or record["cik_observations"] < rules["minimum_issuer_observations"]:
        medium.append("insufficient_dated_issuer_evidence")
    if not record["names_compatible"]:
        medium.append("issuer_name_disagreement_or_missing")
    if record["symbol_count"] > 1 and not record["official_identity"]:
        medium.append("unverified_rename")
    if record["exchange_count"] > 1 and not record["official_identity"]:
        medium.append("unverified_exchange_transfer")
    level = "C" if high else "B" if medium else "A"
    return level, sorted(set(high + medium))


def validate_review_packet(packet, raw_dir: Path, intervals: pd.DataFrame):
    """Install an audit annotation, never a splice or AI-supplied mapping.

    Changing identity facts needs independently parsed security-level facts and
    the existing trust/master rebuild workflow. This channel only annotates.
    """
    fields = {"schema_version", "security_ids", "symbol", "start", "end", "disputed_fact",
              "issuer", "share_class", "exchange", "lifecycle_result", "confidence",
              "classification", "safe_to_merge", "must_remain_separate", "evidence"}
    if not fields <= set(packet) or packet["schema_version"] != 1:
        raise ValueError("incomplete review schema")
    if packet["safe_to_merge"] is not False or packet["must_remain_separate"] is not True:
        raise ValueError("AI annotations cannot splice identity facts")
    if packet["classification"] not in {"A", "B", "C"} or not packet["evidence"]:
        raise ValueError("missing review classification/evidence")
    start, end = date.fromisoformat(packet["start"]), date.fromisoformat(packet["end"])
    if start > end or not packet["security_ids"] or not set(packet["security_ids"]) <= set(intervals.security_id):
        raise ValueError("review identity/date scope invalid")
    validate_intervals(intervals)
    scope = intervals.loc[intervals.security_id.isin(packet["security_ids"])]
    if packet["symbol"] not in set(scope.symbol):
        raise ValueError("review ticker/identity mismatch")
    for sid in packet['security_ids']:
        rows = scope.loc[scope.security_id == sid]
        if not ((pd.to_datetime(rows.valid_from).dt.date <= end) &
                (pd.to_datetime(rows.valid_to).dt.date >= start)).any():
            raise ValueError('review outside observed identity scope')
    for ev in packet["evidence"]:
        if not {"url", "source_version", "sha256", "publication_date", "retrieved_at", "raw_file", "excerpt"} <= set(ev):
            raise ValueError("incomplete source receipt")
        if not ev["url"].startswith("https://") or not ev["source_version"] or not ev["excerpt"]:
            raise ValueError("invalid source")
        published = date.fromisoformat(ev["publication_date"])
        captured = date.fromisoformat(ev["retrieved_at"][:10])
        if published > captured:
            raise ValueError("future evidence publication")
        raw = (raw_dir / ev["raw_file"]).resolve()
        if not raw.is_relative_to(raw_dir.resolve()) or file_hash(raw) != ev["sha256"]:
            raise ValueError("evidence bytes/path mismatch")
        # The excerpt must be present in the actual captured document, not prose
        # invented by an AI. No economics/mapping is installed from this text.
        if ev["excerpt"] not in raw.read_text(encoding="utf-8", errors="replace"):
            raise ValueError("unsupported evidence excerpt")
    return {**packet, "annotation_only": True}


def install_review_annotation(directory, packet, raw_dir, version_root):
    """Copy-on-write, hash-bound installation with the parent left unchanged.

    An annotation documents a conflict and blocks unreviewed derived exports in
    its disputed scope. It cannot assign a new issuer or combine price histories.
    """
    directory, version_root = Path(directory), Path(version_root)
    with HistoricalDatabase(directory) as db:
        intervals = db.connection.execute('SELECT * FROM ticker_episode').df()
        annotation = validate_review_packet(packet, Path(raw_dir), intervals)
        parent = db.manifest
    payload = json.dumps(annotation, ensure_ascii=False, sort_keys=True)
    version = hashlib.sha256((parent['source_version'] + payload + file_hash(Path(__file__))).encode()).hexdigest()
    target = version_root / version
    target.mkdir(parents=True, exist_ok=True)
    if (target / 'manifest.json').exists():
        with HistoricalDatabase(target):
            return target
    source_db = directory / 'historical.duckdb'
    destination = target / 'historical.duckdb'
    shutil.copyfile(source_db, destination)
    with duckdb.connect(str(destination)) as c:
        c.execute('''CREATE TABLE IF NOT EXISTS review_annotation (
            annotation_id VARCHAR PRIMARY KEY, security_id VARCHAR, symbol VARCHAR,
            disputed_start DATE, disputed_end DATE, known_on DATE, evidence_hash VARCHAR,
            classification VARCHAR, annotation_json VARCHAR)''')
        annotation_id = hashlib.sha256(payload.encode()).hexdigest()
        known = max(e['publication_date'] for e in annotation['evidence'])
        evidence_hash = hashlib.sha256(json.dumps(annotation['evidence'],sort_keys=True).encode()).hexdigest()
        for sid in annotation['security_ids']:
            c.execute('INSERT INTO review_annotation VALUES (?,?,?,?,?,?,?,?,?)',
                      [annotation_id + ':' + sid,sid,annotation['symbol'],annotation['start'],annotation['end'],
                       known,evidence_hash,annotation['classification'],payload])
            # Conservative quality quarantine, not a new identity/lifecycle fact.
            # No future publication can alter an earlier decision session.
            columns={r[0] for r in c.execute('DESCRIBE daily_population').fetchall()}
            if 'evidence_conflict' in columns:
                c.execute("""UPDATE daily_population SET membership_status='unknown',evidence_conflict=true
                    WHERE security_id=? AND date BETWEEN ? AND ? AND date>=?""",
                          [sid,annotation['start'],annotation['end'],known])
        tables={r[0] for r in c.execute('SHOW TABLES').fetchall()}
        if 'daily_scorecard' in tables:
            c.execute("""CREATE OR REPLACE TABLE daily_scorecard AS SELECT date,count(*) AS observed_population,
                count(*) FILTER(WHERE security_type='common') AS common_population,
                count(*) FILTER(WHERE security_type='unknown') AS class_unknown,
                count(*) FILTER(WHERE membership_status='confirmed_member') AS confirmed,
                count(*) FILTER(WHERE membership_status='probable_member') AS probable,
                count(*) FILTER(WHERE membership_status='unknown') AS unknown,
                count(*) FILTER(WHERE evidence_conflict) AS conflicts FROM daily_population GROUP BY date ORDER BY date""")
        c.execute('CHECKPOINT')
    for name in ('rules.json','dividends.json'):
        if (directory/name).exists():
            shutil.copyfile(directory/name,target/name)
    manifest = {**parent,'source_version':version,'database_sha256':file_hash(destination),
                'parent_version':parent['source_version'],'parent_database_sha256':parent['database_sha256'],
                'review_annotation_sha256':annotation_id,'annotation_only':True}
    (target/'identity-resolution.json').write_text(payload,encoding='utf-8')
    (target/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    if file_hash(source_db) != parent['database_sha256']:
        raise ValueError('parent database changed during annotation installation')
    return target


class HistoricalDatabase:
    """Read-only population and homogeneous price-series access.

    IDs match LocalSecurityMaster and PIT features. Population keeps all types
    and uncertainty. Use common_candidates_on for ordinary-stock research.
    """
    def __init__(self, directory: Path, *, verify=True):
        self.directory = Path(directory)
        self.manifest = json.loads((self.directory / "manifest.json").read_text(encoding="utf-8"))
        if self.manifest.get("schema_version") != 1:
            raise ValueError("unsupported database manifest")
        path = self.directory / "historical.duckdb"
        if verify and file_hash(path) != self.manifest["database_sha256"]:
            raise ValueError("historical database mutated")
        self.connection = duckdb.connect(str(path), read_only=True)

    def close(self):
        self.connection.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    @property
    def fingerprint(self):
        return self.manifest["source_version"]

    def population_on(self, day, *, include_unknown=True):
        d = date.fromisoformat(str(day)[:10])
        if not self.manifest["coverage_start"] <= str(d) <= self.manifest["coverage_end"]:
            raise ValueError("date outside reconstructed coverage")
        if not self.connection.execute("SELECT count(*) FROM sessions WHERE date=?", [d]).fetchone()[0]:
            raise ValueError("date not in observed session calendar")
        frame = self.connection.execute("SELECT * FROM daily_population WHERE date=? ORDER BY security_id", [d]).df()
        if not include_unknown:
            frame = frame.loc[frame.membership_status != "unknown"]
        frame["member"] = pd.array([membership_truth(s) for s in frame.membership_status], dtype="boolean")
        return frame

    def common_candidates_on(self, day):
        """Unknown classification stays visible alongside common candidates."""
        f = self.population_on(day)
        return f.loc[f.security_type.isin(["common", "unknown"])]

    def uncertainty_on(self, day):
        """Previously observed, now absent IDs without a proven cessation.

        Keep this uncertainty set alongside the observed population. It is not
        a claim that all these candidates are still listed. In particular, a
        missing directory row and a proven legal delisting are different facts.
        Future first observations are never pulled back into the past.
        """
        self.validate_coverage([day])
        d=date.fromisoformat(str(day)[:10])
        f=self.connection.execute("""WITH last_rows AS (SELECT *,row_number() OVER
            (PARTITION BY security_id ORDER BY valid_to DESC) AS n FROM ticker_episode WHERE valid_from<=?)
            SELECT security_id,symbol,exchange,security_type,eligible AS last_observed_eligible,
                valid_to AS last_observed_date FROM last_rows m WHERE n=1 AND valid_to<?
            AND NOT EXISTS(SELECT 1 FROM lifecycle_event e WHERE e.security_id=m.security_id
                AND e.confidence='verified' AND e.event_type IN
                ('trading_suspension','delisting','termination','equity_cancellation') AND e.effective_date<=?)
            ORDER BY security_id""",[d,d,d]).df()
        f['date']=pd.Timestamp(d)
        f['membership_status']='unknown'
        f['member']=pd.array([pd.NA]*len(f),dtype='boolean')
        f['reason']='observation ended; no verified cessation; identity fragmentation also possible'
        return f

    def candidate_population_on(self, day):
        """Observed population plus explicit prior-observation uncertainty."""
        return pd.concat([self.population_on(day),self.uncertainty_on(day)],ignore_index=True)

    def membership_on(self, security_id, day):
        f = self.population_on(day)
        matched = f.loc[f.security_id == security_id]
        if not matched.empty:
            return matched.iloc[0].membership_status
        # Observational absence never proves nonexistence. Only documented
        # listing/suspension/cancellation establishes a nonmember boundary.
        row = self.connection.execute("""SELECT event_type,effective_date FROM lifecycle_event
            WHERE security_id=? AND confidence='verified' AND event_type IN
            ('listing','trading_suspension','delisting','termination','equity_cancellation')""", [security_id]).fetchall()
        d = date.fromisoformat(str(day)[:10])
        if any((kind == "listing" and d < when) or (kind != "listing" and d >= when) for kind, when in row):
            return "confirmed_non_member"
        return "unknown"

    def validate_coverage(self, sessions):
        days = sorted({str(v)[:10] for v in sessions})
        if not days:
            raise ValueError('coverage requires observed sessions')
        actual = {str(v[0]) for v in self.connection.execute('SELECT date FROM sessions').fetchall()}
        if not set(days) <= actual:
            raise ValueError('historical database session coverage gap')

    def eligible_on(self, day):
        """Protocol adapter: source eligibility only, independent of future risk."""
        f = self.population_on(day)
        return f.loc[f.eligible & f.membership_status.ne('confirmed_non_member')]

    def prices(self, security_id, start, end, *, basis="raw"):
        if basis != "raw":
            raise ValueError("accepted reader only exposes homogeneous raw prices")
        f = self.connection.execute("""SELECT * FROM accepted_price WHERE security_id=?
            AND date BETWEEN ? AND ? ORDER BY date""", [security_id, start, end]).df()
        validate_prices(f)
        if not f.empty:
            self.filter_frame(f)  # identity/date checks also apply to raw prices
        return f

    def filter_frame(self, frame: pd.DataFrame):
        """Safe ID-bound adapter for prices/features; no future audit filter.

        Keeps uncertain rows and returns explicit population status. Consumers
        choose a policy; this adapter cannot silently discard uncertainty.
        """
        f = frame.reset_index(drop=True).copy()
        if not {"security_id", "symbol", "date"} <= set(f):
            raise ValueError("historical adapter requires explicit identity")
        f["date"] = pd.to_datetime(f.date).dt.date
        self.connection.register("input_frame", f)
        try:
            tables = {r[0] for r in self.connection.execute('SHOW TABLES').fetchall()}
            if 'issuer_evidence' in tables:
                conflict = self.connection.execute('''SELECT count(*) FROM (
                    SELECT i.security_id,i.date FROM input_frame i JOIN issuer_evidence e
                    ON i.security_id=e.security_id AND CAST(e.available_on AS DATE)<=i.date
                    GROUP BY i.security_id,i.date HAVING count(DISTINCT e.cik)>1)''').fetchone()[0]
                if conflict:
                    raise ValueError('issuer conflict known by this session; identity rebuild required')
            result = self.connection.execute("""SELECT i.*,p.membership_status,p.security_type,
                p.exchange AS historical_exchange FROM input_frame i JOIN daily_population p
                ON i.security_id=p.security_id AND i.symbol=p.symbol AND i.date=p.date""").df()
        finally:
            self.connection.unregister("input_frame")
        if len(result) != len(f):
            raise ValueError("price/feature identity/date outside historical population")
        # A documented identity discontinuity must not pass silently into ML or
        # a new strategy simply because the old master still has one legacy ID.
        if 'review_annotation' in tables:
            annotations = self.connection.execute('SELECT security_id,disputed_start,disputed_end,known_on FROM review_annotation').fetchall()
            for sid,start,end,known in annotations:
                days = pd.to_datetime(result.date).dt.date
                if (result.security_id.eq(sid) & days.between(start,end) & days.ge(known)).any():
                    raise ValueError('reviewed identity discontinuity; rebuild features with separate security identities')
        return result

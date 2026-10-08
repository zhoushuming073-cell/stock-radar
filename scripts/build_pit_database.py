"""Build a content-addressed historical database without promoting a master.

No strategy configuration, original price/feature store or identity is changed.
Raw public data stays local. A failed build never creates a published manifest.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re

import duckdb
import pandas as pd

from radar.lab.universe import LocalSecurityMaster
from radar.pit.builder import digest
from radar.pit.database import classify_episode, compatible_name, validate_intervals, validate_prices
from radar.pit.features import file_hash


def literal(value):
    return "'" + str(value).replace("'", "''") + "'"


def load_json(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(root: Path):
    rules_path = root / "config/pit_database_rules.json"
    rules = load_json(rules_path)
    master = LocalSecurityMaster(root / "data/security-master.csv", root / "data/security-master-manifest.json")
    normalized = root / "data/pit/normalized" / master.manifest["source_version"]
    refs = root / "data/pit/construction/references"
    research = root / "data/pit/research-grade"
    paths = {
        "master": master.csv_path, "master_manifest": master.manifest_path,
        "rules": rules_path, "trust": root / "config/pit_trust_evidence.json",
        "references": refs / "observations.parquet", "reference_evidence": refs / "evidence.json",
        "snapshot_audit": normalized / "snapshot-audit.json",
        "accepted_prices": research / "accepted-prices.duckdb",
        "accepted_manifest": research / "accepted-prices.manifest.json",
        "raw_prices": research / "raw-source.duckdb", "raw_manifest": research / "raw-source.manifest.json",
        "feature_store": normalized / "pit-research.duckdb",
        "external_prices": normalized / "external-prices.duckdb",
        "splits": research / "split-scan.json", "dividends": research / "dividend-scan.json",
        "disagreements": research / "source-disagreement.json", "market_calendar": root / "data/market.duckdb",
        "builder_code": Path(__file__).resolve(), "database_code": root / "src/radar/pit/database.py",
    }
    # Keep the existing source bytes locked, including source manifests.
    hashes = {name: file_hash(path) for name, path in paths.items()}
    accepted_manifest = load_json(paths["accepted_manifest"])
    raw_manifest = load_json(paths["raw_manifest"])
    if hashes["accepted_prices"] != accepted_manifest["database_sha256"] or hashes["raw_prices"] != raw_manifest["database_sha256"]:
        raise ValueError("existing accepted/raw source lock differs")
    evidence = load_json(paths["reference_evidence"])
    for ev in evidence:
        if file_hash(Path(ev["raw_path"])) != ev["raw_sha256"]:
            raise ValueError("reference source bytes mutated")
    version = digest({"schema_version": 1, "inputs": hashes})
    directory = root / "data/pit/construction/versions" / version
    directory.mkdir(parents=True, exist_ok=True)
    if (directory / "manifest.json").exists():
        if load_json(directory / "manifest.json")["database_sha256"] != file_hash(directory / "historical.duckdb"):
            raise ValueError("published database mutated")
        print(json.dumps({"existing": str(directory), "source_version": version}), flush=True)
        return directory
    path = directory / "historical.duckdb"
    # Only remove this precise unfinished output file, not any source directory.
    if path.exists():
        path.unlink()
    frame = pd.read_csv(master.csv_path, keep_default_na=False)
    validate_intervals(frame)
    for col in ("valid_from", "valid_to", "listing_date", "delisting_date"):
        frame[col] = pd.to_datetime(frame[col].replace("", None)).dt.date
    frame["eligible"] = frame.eligible.astype(str).str.lower().isin(["true", "1"])
    frame["interval_id"] = [digest({"id": r.security_id, "symbol": r.symbol, "from": str(r.valid_from), "to": str(r.valid_to)})
                            for r in frame.itertuples()]
    frame["evidence_hash"] = hashes["master"]
    def class_description(row):
        if row.share_class:
            return row.share_class
        match=re.search(r'(?i)(class\s+[a-z0-9-]+.*|common stock.*|ordinary shares.*|american depositary.*|warrants?.*|units?.*)',row.security_name)
        return match.group(0) if match else 'unresolved class description'
    frame['class_description']=[class_description(r) for r in frame.itertuples()]
    trust = load_json(paths["trust"])
    disagreements = load_json(paths["disagreements"])
    conflicts = pd.DataFrame({"security_id": [r["security_id"] for r in disagreements if r.get("disagreements", 0) > 0]})
    c = duckdb.connect(str(path))
    try:
        c.execute("SET threads=4")
        c.execute("SET memory_limit='3GB'")
        c.register("master_frame", frame)
        c.execute("CREATE TABLE ticker_episode AS SELECT * FROM master_frame")
        c.execute("CREATE TABLE reference_observation AS SELECT * FROM read_parquet(?)", [str(paths["references"])])
        c.register("evidence_frame", pd.DataFrame(evidence).drop(columns="rows"))
        c.execute("CREATE TABLE evidence AS SELECT * FROM evidence_frame")
        c.register("conflict_frame", conflicts)
        c.execute("CREATE TABLE price_conflict AS SELECT * FROM conflict_frame")
        for alias, name in (("rawsrc", "raw_prices"), ("accepted", "accepted_prices"),
                            ("features", "feature_store"), ("external", "external_prices"), ("market", "market_calendar")):
            c.execute("ATTACH " + literal(paths[name]) + " AS " + alias + " (READ_ONLY)")
        c.execute("""CREATE TABLE sessions AS SELECT DISTINCT date FROM market.daily_bars
            WHERE symbol='SPY' AND date BETWEEN ? AND ? ORDER BY date""",
                  [master.coverage_start.date(), master.coverage_end.date()])
        calendar = c.execute("SELECT min(date),max(date),count(*) FROM sessions").fetchone()
        if str(calendar[0]) != str(master.coverage_start.date()) or str(calendar[1]) != str(master.coverage_end.date()):
            raise ValueError("observed calendar does not span requested database coverage")
        c.execute("""CREATE TABLE linked_observation AS SELECT r.*,m.security_id,m.interval_id,
            m.security_name,m.exchange AS primary_exchange,m.security_type
            FROM reference_observation r JOIN ticker_episode m ON r.symbol=m.symbol
            AND CAST(r.available_on AS DATE) BETWEEN m.valid_from AND m.valid_to""")
        pairs = c.execute("SELECT DISTINCT name,security_name FROM linked_observation").fetchall()
        names = pd.DataFrame([(a, b, compatible_name(a, b)) for a, b in pairs], columns=["name", "security_name", "compatible"])
        c.register("name_frame", names)
        c.execute("CREATE TABLE name_crosscheck AS SELECT * FROM name_frame")
        c.execute("""CREATE TABLE issuer_evidence AS SELECT l.*,n.compatible AS name_compatible,
            (l.exchange=l.primary_exchange OR (l.exchange='NYSE MKT' AND l.primary_exchange='AMEX')) AS exchange_compatible
            FROM linked_observation l JOIN name_crosscheck n USING(name,security_name) WHERE source='cik'""")
        c.execute("""CREATE TABLE issuer_conflict_boundary AS WITH firsts AS (
            SELECT security_id,cik,min(CAST(available_on AS DATE)) AS first_known FROM issuer_evidence GROUP BY 1,2),
            ranked AS (SELECT *,row_number() OVER(PARTITION BY security_id ORDER BY first_known,cik) AS n FROM firsts)
            SELECT security_id,first_known AS conflict_known_on FROM ranked WHERE n=2""")
        c.execute("""CREATE TABLE membership_evidence AS SELECT l.*,n.compatible AS name_compatible,
            (l.exchange=l.primary_exchange OR (l.exchange='NYSE MKT' AND l.primary_exchange='AMEX')) AS exchange_compatible
            FROM linked_observation l JOIN name_crosscheck n USING(name,security_name)
            WHERE source='cik' OR (source='nasdaq'
                AND regexp_matches(name,'(?i)(common stock|ordinary shares)')
                AND NOT regexp_matches(name,'(?i)(ETF|test issue|test stock|depositary)'))""")
        c.execute("""CREATE TABLE security_episode AS WITH ordered AS (
            SELECT *,CASE WHEN valid_from <= lag(valid_to) OVER(PARTITION BY security_id ORDER BY valid_from)+1
                THEN 0 ELSE 1 END AS boundary FROM ticker_episode), groups AS (
            SELECT *,sum(boundary) OVER(PARTITION BY security_id ORDER BY valid_from) AS episode_index FROM ordered)
            SELECT security_id,security_id||':'||episode_index::VARCHAR AS episode_id,
                min(valid_from) AS episode_start,max(valid_to) AS episode_end,
                string_agg(DISTINCT symbol,',' ORDER BY symbol) AS historical_tickers,
                string_agg(DISTINCT exchange,',' ORDER BY exchange) AS exchanges,
                string_agg(DISTINCT security_type,',' ORDER BY security_type) AS security_types,
                string_agg(DISTINCT security_name,' | ' ORDER BY security_name) AS issuer_names,
                string_agg(DISTINCT share_class,',' ORDER BY share_class) AS share_classes,
                string_agg(DISTINCT class_description,' | ' ORDER BY class_description) AS share_class_description,
                min(listing_date) AS documented_listing_date,max(delisting_date) AS documented_last_tradable_date,
                string_agg(DISTINCT evidence_hash,',') AS evidence_hash
            FROM groups GROUP BY security_id,episode_index""")
        print("Built intervals and dated issuer links", flush=True)
        event_rows = []
        for ev in trust["events"]:
            kind = {"symbol_change": "ticker_change", "cash_dividend": "dividend"}.get(ev["event_type"], ev["event_type"])
            src = trust["sources"][ev["source"]]
            event_rows.append({"security_id": ev["security_id"], "event_type": kind,
                "effective_date": ev["effective_date"], "confidence": ev["confidence"], "source": ev["source"],
                "source_version": src["source_version"], "evidence_url": src["url"], "evidence_hash": src["raw_sha256"],
                "known_on": None, "known_on_status": "not_parsed_from_legacy_source; retrospective_only",
                "details": json.dumps(ev, sort_keys=True), "economics_enabled": False})
        # Dates of public announcements and effect are distinct. Legacy sources
        # without parsed publication dates cannot be used as causal predictors.
        by_symbol = {symbol: list(group.itertuples()) for symbol, group in frame.groupby("symbol")}
        for ev in load_json(paths["splits"])["events"]:
            day = ev["date"][:10]
            matches = [r.security_id for r in by_symbol.get(ev["symbol"], []) if str(r.valid_from) <= day <= str(r.valid_to)]
            for sid in matches:
                event_rows.append({"security_id": sid, "event_type": "reverse_split" if ev["to_factor"] < ev["for_factor"] else "split",
                    "effective_date": day, "confidence": "candidate", "source": "Dolt split table",
                    "source_version": raw_manifest["source_version"], "evidence_url": "https://www.dolthub.com/repositories/post-no-preference/stocks",
                    "evidence_hash": hashes["splits"], "known_on": None, "known_on_status": "announcement_date_unavailable",
                    "details": json.dumps(ev, sort_keys=True), "economics_enabled": False})
        events = pd.DataFrame(event_rows)
        events.effective_date = pd.to_datetime(events.effective_date).dt.date
        c.register("event_frame", events)
        c.execute("""CREATE TABLE lifecycle_event AS SELECT security_id,event_type,effective_date,confidence,source,
            source_version,evidence_url,evidence_hash,CAST(known_on AS DATE) AS known_on,known_on_status,details,economics_enabled,
            sha256(security_id||event_type||effective_date::VARCHAR||source) AS event_id FROM event_frame""")
        transitions = []
        for sid, group in frame.groupby('security_id', sort=True):
            if len(group)<2:
                continue
            prior = None
            for r in group.sort_values('valid_from').itertuples():
                if prior:
                    for field,kind in (('symbol','ticker_change'),('exchange','exchange_transfer'),
                                       ('security_type','class_transition'),('security_name','name_change')):
                        if getattr(r,field) != getattr(prior,field):
                            transitions.append({'security_id':sid,'event_type':kind,'effective_date':r.valid_from,
                                'confidence':'candidate','source':'historical interval transition',
                                'source_version':master.manifest['source_version'],
                                'evidence_url':'https://github.com/rreichel3/US-Stock-Symbols',
                                'evidence_hash':hashes['master'],'known_on':r.valid_from,
                                'known_on_status':'observed transition; legal effective date unverified',
                                'details':json.dumps({'old':str(getattr(prior,field)),'new':str(getattr(r,field))}),
                                'economics_enabled':False})
                prior = r
        if transitions:
            c.register('transition_frame',pd.DataFrame(transitions))
            c.execute('''INSERT INTO lifecycle_event SELECT t.*,sha256(security_id||event_type||effective_date::VARCHAR||source)
                FROM transition_frame t WHERE NOT EXISTS(SELECT 1 FROM lifecycle_event e
                WHERE e.security_id=t.security_id AND e.event_type=t.event_type AND e.effective_date=t.effective_date)''')
        c.execute("""CREATE TABLE accepted_price AS SELECT p.security_id,p.symbol,p.date,p.open,p.high,p.low,p.close,p.volume,
            p.provider AS source,? AS source_version,p.downloaded_at AS retrieved_at,p.adjustment AS basis,
            'source_raw; events separate; no synthetic adjustment' AS action_relation,
            CASE WHEN x.security_id IS NULL THEN 'no_detected_source_conflict_in_available_comparison'
                ELSE 'comparison_conflict; no winner chosen' END AS conflict_state,
            ? AS source_database_sha256
            FROM accepted.daily_bars p LEFT JOIN price_conflict x USING(security_id)""",
                  [accepted_manifest["source_version"], hashes["accepted_prices"]])
        validate_prices(c.execute("SELECT * FROM accepted_price").df())
        invalid = c.execute("""SELECT count(*) FROM accepted_price p LEFT JOIN ticker_episode m
            ON p.security_id=m.security_id AND p.symbol=m.symbol AND p.date BETWEEN m.valid_from AND m.valid_to
            WHERE m.security_id IS NULL""").fetchone()[0]
        if invalid:
            raise ValueError("accepted price identity interval mismatch")
        c.execute("""CREATE TABLE observed_price AS SELECT p.security_id,p.symbol,p.date,p.adjustment AS basis,
            'legacy PIT feature input; independently bounded series' AS source,? AS source_database_sha256
            FROM features.daily_bars p UNION ALL SELECT security_id,symbol,date,adjustment,
            'official identity bounded external; separate basis',? FROM external.daily_bars""",
                  [hashes["feature_store"], hashes["external_prices"]])
        # Quarantine stays quarantine; a ticker/date hit is availability, not an
        # identity decision. Do not copy these OHLC rows into accepted_price.
        c.execute("""CREATE TABLE raw_price_hit AS SELECT m.security_id,p.symbol,p.date FROM rawsrc.daily_bars p
            JOIN ticker_episode m ON p.symbol=m.symbol AND p.date BETWEEN m.valid_from AND m.valid_to""")
        c.execute("""CREATE TABLE feature_presence AS SELECT security_id,symbol,date,tradability_pass
            FROM features.daily_features""")
        c.execute("""CREATE TABLE price_anomaly AS WITH p AS (SELECT m.security_id,p.date,p.volume,p.open,p.close,
            lag(p.date) OVER h AS prior_date,lag(p.close) OVER h AS prior_close,lag(p.volume) OVER h AS prior_volume
            FROM rawsrc.daily_bars p JOIN ticker_episode m ON p.symbol=m.symbol AND p.date BETWEEN m.valid_from AND m.valid_to
            WINDOW h AS (PARTITION BY m.security_id ORDER BY p.date))
            SELECT security_id,date,CASE WHEN volume=0 THEN 'zero_volume'
                WHEN date-prior_date>? THEN 'long_trading_gap'
                WHEN open/prior_close>? OR open/prior_close<? THEN 'price_jump_or_split_like'
                ELSE 'extreme_volume' END AS reason FROM p WHERE volume=0 OR date-prior_date>?
                OR open/prior_close>? OR open/prior_close<? OR volume/nullif(prior_volume,0)>100""",
                  [rules["long_gap_calendar_days"], rules["jump_high"], rules["jump_low"],
                   rules["long_gap_calendar_days"], rules["jump_high"], rules["jump_low"]])
        records = c.execute("""WITH ids AS (SELECT security_id,min(valid_from) AS first_date,max(valid_to) AS last_date,
            count(DISTINCT symbol) AS symbol_count,count(DISTINCT exchange) AS exchange_count,
            count(DISTINCT security_type) AS type_count,
            CASE WHEN bool_or(security_type='common') THEN 'common' ELSE min(security_type) END AS security_type,
            bool_or(resolution_status='verified') AS official_identity FROM ticker_episode GROUP BY security_id),
            reuse AS (SELECT symbol,count(DISTINCT security_id) AS n FROM ticker_episode GROUP BY symbol),
            risk AS (SELECT security_id,max(n) AS ticker_episode_count FROM ticker_episode JOIN reuse USING(symbol) GROUP BY security_id),
            issuer AS (SELECT security_id,count(DISTINCT cik) AS cik_count,count(*) AS cik_observations,
                bool_and(name_compatible AND exchange_compatible) AS names_compatible,
                string_agg(DISTINCT cik,',' ORDER BY cik) AS ciks FROM issuer_evidence GROUP BY security_id)
            SELECT ids.*,risk.ticker_episode_count,coalesce(issuer.cik_count,0) AS cik_count,
                coalesce(issuer.cik_observations,0) AS cik_observations,coalesce(issuer.names_compatible,false) AS names_compatible,
                coalesce(issuer.ciks,'') AS ciks,last_date<? AS disappeared,
                EXISTS(SELECT 1 FROM lifecycle_event e WHERE e.security_id=ids.security_id AND confidence='verified'
                    AND event_type IN ('trading_suspension','delisting','termination','merger')) AS official_terminal,
                EXISTS(SELECT 1 FROM lifecycle_event e WHERE e.security_id=ids.security_id AND confidence!='verified') AS material_unresolved,
                EXISTS(SELECT 1 FROM price_anomaly p WHERE p.security_id=ids.security_id) AS price_anomaly,
                EXISTS(SELECT 1 FROM price_conflict p WHERE p.security_id=ids.security_id) AS price_conflict
            FROM ids JOIN risk USING(security_id) LEFT JOIN issuer USING(security_id) ORDER BY security_id""",
                  [master.coverage_end.date()]).df()
        labels = [classify_episode(r, rules) for r in records.to_dict("records")]
        records["level"] = [v[0] for v in labels]
        records["reasons"] = [json.dumps(v[1]) for v in labels]
        records["research_identity_pass"] = records.level == "A"
        records["scope"] = "full-window audit only; forbidden as historical selection predicate"
        c.register("risk_frame", records)
        c.execute("CREATE TABLE identity_quality AS SELECT * FROM risk_frame")
        print("Built identity risk, accepted prices and anomalies", flush=True)
        snapshots = pd.DataFrame([{"date": s["date"], "commit": s["commit"], "evidence_hash": digest(s["file_hashes"])}
                                 for s in load_json(paths["snapshot_audit"])["snapshots"] if s["accepted"]])
        snapshots["date"] = pd.to_datetime(snapshots.date).dt.date
        c.register("snapshot_frame", snapshots)
        c.execute("CREATE TABLE primary_snapshot AS SELECT * FROM snapshot_frame")
        c.execute("""CREATE TABLE primary_calendar AS SELECT date,(SELECT max(p.date) FROM primary_snapshot p WHERE p.date<=s.date)
            AS latest_primary FROM sessions s""")
        # Only contemporaneously available observations corroborate each day.
        # This creates positive observations, not the Cartesian product of every
        # future security and every historical day. Outside it remains unknown.
        c.execute("""CREATE TABLE daily_population AS WITH primary_days AS (
            SELECT s.date,m.security_id,m.symbol,m.exchange,m.security_type,m.eligible,m.interval_id,
                m.valid_from,m.valid_to,s.latest_primary,m.evidence_hash,
                CASE WHEN m.listing_date>s.date OR m.delisting_date<s.date THEN true ELSE false END AS boundary_violation
            FROM primary_calendar s JOIN ticker_episode m ON s.date BETWEEN m.valid_from AND m.valid_to),
            refs AS (SELECT p.date,p.security_id,count(DISTINCT nullif(i.cik,'')) AS ciks,
                bool_or(i.name_compatible AND i.exchange_compatible) AS corroborated,
                bool_or(NOT i.name_compatible OR NOT i.exchange_compatible) AS conflict
                FROM primary_days p JOIN membership_evidence i ON p.security_id=i.security_id AND p.interval_id=i.interval_id
                AND CAST(i.available_on AS DATE)<=p.date AND p.date-CAST(i.available_on AS DATE)<=?
                GROUP BY p.date,p.security_id)
            SELECT p.*,CASE WHEN boundary_violation THEN 'confirmed_non_member'
                WHEN date-latest_primary>? OR latest_primary IS NULL THEN 'unknown'
                WHEN p.date>=b.conflict_known_on OR r.ciks>1 OR coalesce(r.conflict,false) THEN 'unknown'
                WHEN r.corroborated THEN 'confirmed_member'
                ELSE 'probable_member' END AS membership_status,
                CASE WHEN p.date>=b.conflict_known_on OR r.ciks>1 OR coalesce(r.conflict,false) THEN true ELSE false END AS evidence_conflict
            FROM primary_days p LEFT JOIN refs r USING(date,security_id)
            LEFT JOIN issuer_conflict_boundary b USING(security_id)""",
                  [rules["fresh_reference_days"], rules["fresh_primary_days"]])
        c.execute("""CREATE TABLE daily_scorecard AS SELECT date,count(*) AS observed_population,
            count(*) FILTER(WHERE security_type='common') AS common_population,
            count(*) FILTER(WHERE security_type='unknown') AS class_unknown,
            count(*) FILTER(WHERE membership_status='confirmed_member') AS confirmed,
            count(*) FILTER(WHERE membership_status='probable_member') AS probable,
            count(*) FILTER(WHERE membership_status='unknown') AS unknown,
            count(*) FILTER(WHERE evidence_conflict) AS conflicts
            FROM daily_population GROUP BY date ORDER BY date""")
        queue = []
        for r in records.to_dict("records"):
            if r["level"] != "A":
                for reason in json.loads(r["reasons"]):
                    queue.append({"security_id": r["security_id"], "start": str(r["first_date"])[:10], "end": str(r["last_date"])[:10],
                                  "reason": reason, "level": r["level"], "scope": "common" if r["security_type"] == "common" else "other_class",
                                  "evidence_hash": hashes["master"], "status": "unresolved"})
        for r in c.execute("SELECT security_id,date,reason FROM price_anomaly").fetchall():
            queue.append({"security_id": r[0], "start": str(r[1]), "end": str(r[1]), "reason": r[2], "level": "B",
                          "scope": "price", "evidence_hash": hashes["raw_prices"], "status": "unresolved"})
        c.register("queue_frame", pd.DataFrame(queue))
        c.execute('CREATE TABLE identity_lifecycle_review_queue AS SELECT *,sha256(security_id||start||"end"||reason) AS queue_id FROM queue_frame')
        # Observation end is a candidate event. It never cancels a security.
        c.execute("""INSERT INTO lifecycle_event SELECT security_id,'observation_end',last_date,'candidate',
            'primary historical snapshots',?,'https://github.com/rreichel3/US-Stock-Symbols',?,
            NULL,'first missing observation is not a legal delisting',reasons,false,
            sha256(security_id||'observation_end') FROM identity_quality WHERE disappeared AND NOT official_terminal""",
                  [master.manifest["source_version"], hashes["master"]])
        c.execute("""INSERT INTO lifecycle_event SELECT security_id,'new_observation',first_date,'candidate',
            'primary historical snapshots',?,'https://github.com/rreichel3/US-Stock-Symbols',?,
            first_date,'first observation is not IPO date',reasons,false,
            sha256(security_id||'new_observation') FROM identity_quality WHERE first_date>?""",
                  [master.manifest['source_version'],hashes['master'],master.coverage_start.date()])
        # Every relational edge carries bounded dates, source bytes and confidence.
        c.execute("""CREATE TABLE evidence_graph AS SELECT 'security:'||security_id AS from_node,
            'ticker:'||interval_id AS to_node,'observed_ticker' AS relation,valid_from,valid_to,
            valid_from AS known_on,'primary snapshot interval' AS source,first_source_commit AS source_version,
            evidence_hash,'observed' AS confidence FROM ticker_episode
            UNION ALL SELECT 'ticker:'||interval_id,'exchange:'||exchange||':'||interval_id,'listed_on',
            valid_from,valid_to,valid_from,'primary snapshot interval',first_source_commit,evidence_hash,'observed' FROM ticker_episode
            UNION ALL SELECT 'issuer:CIK-'||i.cik,'security:'||i.security_id,'candidate_same_issuer',
            CAST(i.available_on AS DATE),CAST(i.available_on AS DATE),CAST(i.available_on AS DATE),e.source,e.source_version,e.raw_sha256,
            CASE WHEN name_compatible AND exchange_compatible THEN 'corroborated' ELSE 'conflicting' END
            FROM issuer_evidence i JOIN evidence e USING(evidence_id)
            UNION ALL SELECT 'security:'||security_id,'class:'||share_class||':'||security_id,'same_class',
            valid_from,valid_to,NULL,'reviewed legacy security mapping',identity_resolution_method,identity_evidence_hash,'verified_retrospective'
            FROM ticker_episode WHERE resolution_status='verified' AND share_class!=''
            UNION ALL SELECT 'security:'||security_id,'price-series:'||security_id||':raw','raw_price_series',
            min(date),max(date),NULL,'accepted raw source',?,?,'accepted_research_scope' FROM accepted_price GROUP BY security_id""",
                  [accepted_manifest["source_version"], hashes["accepted_prices"]])
        c.execute("""INSERT INTO evidence_graph SELECT 'security:'||security_id,'lifecycle:'||event_id,
            event_type,effective_date,effective_date,CAST(known_on AS DATE),source,source_version,evidence_hash,confidence
            FROM lifecycle_event""")
        c.execute("""INSERT INTO evidence_graph SELECT 'security:'||security_id,
            'class-description:'||security_id||':'||sha256(class_description),'observed_class_description',
            valid_from,valid_to,valid_from,'primary security description',first_source_commit,evidence_hash,'observed_descriptor'
            FROM ticker_episode UNION ALL SELECT 'class-description:'||security_id||':'||sha256(class_description),
            'ticker:'||interval_id,'ticker_of_observed_class',valid_from,valid_to,valid_from,
            'primary security description',first_source_commit,evidence_hash,'observed_descriptor' FROM ticker_episode
            UNION ALL SELECT 'exchange:'||m.exchange||':'||m.interval_id,'price-series:'||m.security_id||':raw',
            'price_on_exchange_interval',greatest(m.valid_from,p.first_date),least(m.valid_to,p.last_date),NULL,
            'accepted price + primary exchange interval',m.first_source_commit,m.evidence_hash,'accepted_research_scope'
            FROM ticker_episode m JOIN (SELECT security_id,min(date) AS first_date,max(date) AS last_date FROM accepted_price GROUP BY 1) p
            ON m.security_id=p.security_id AND m.valid_from<=p.last_date AND m.valid_to>=p.first_date""")
        c.execute("""ALTER TABLE security_episode ADD COLUMN ciks VARCHAR;
            ALTER TABLE security_episode ADD COLUMN confidence VARCHAR;
            ALTER TABLE security_episode ADD COLUMN listing_evidence VARCHAR;
            ALTER TABLE security_episode ADD COLUMN delisting_evidence VARCHAR;
            ALTER TABLE security_episode ADD COLUMN rename_evidence VARCHAR;
            ALTER TABLE security_episode ADD COLUMN predecessor VARCHAR;
            ALTER TABLE security_episode ADD COLUMN successor VARCHAR""")
        c.execute("""ALTER TABLE security_episode ADD COLUMN source_evidence_ids VARCHAR;
            ALTER TABLE security_episode ADD COLUMN source_dates VARCHAR""")
        c.execute("UPDATE security_episode SET ciks=q.ciks,confidence=q.level FROM identity_quality q WHERE security_episode.security_id=q.security_id")
        c.execute("""UPDATE security_episode SET source_evidence_ids=e.ids,source_dates=e.days FROM (
            SELECT security_id,string_agg(DISTINCT evidence_id,',' ORDER BY evidence_id) AS ids,
                string_agg(DISTINCT available_on,',' ORDER BY available_on) AS days FROM linked_observation GROUP BY security_id) e
            WHERE security_episode.security_id=e.security_id""")
        for column, kinds in (("listing_evidence", "'listing'"), ("delisting_evidence", "'trading_suspension','delisting','termination'"),
                              ("rename_evidence", "'ticker_change'")):
            c.execute(f"""UPDATE security_episode SET {column}=e.ids FROM (SELECT security_id,string_agg(event_id,',') AS ids
                FROM lifecycle_event WHERE confidence='verified' AND event_type IN ({kinds}) GROUP BY security_id) e
                WHERE security_episode.security_id=e.security_id""")
        # Unknown predecessor/successor stays NULL, never inferred from ticker.
        dividend = load_json(paths["dividends"])
        if dividend.get('events'):
            dividends = pd.DataFrame(dividend['events'])
            dividends['date'] = pd.to_datetime(dividends['date']).dt.date
            c.register('dividend_frame', dividends)
            c.execute("""CREATE TABLE cash_dividend AS SELECT d.*,m.security_id,? AS evidence_hash,
                'candidate; ordinary dividend impact assessed separately' AS confidence
                FROM dividend_frame d LEFT JOIN ticker_episode m ON d.symbol=m.symbol
                AND d.date BETWEEN m.valid_from AND m.valid_to""",[hashes['dividends']])
        (directory / "dividends.json").write_text(json.dumps(dividend, ensure_ascii=False), encoding="utf-8")
        (directory / "rules.json").write_text(json.dumps(rules, indent=2), encoding="utf-8")
        counts = {t: c.execute("SELECT count(*) FROM " + t).fetchone()[0] for t in
                  ("security_episode", "ticker_episode", "daily_population", "reference_observation", "issuer_evidence", "evidence_graph",
                   "identity_quality", "accepted_price", "raw_price_hit", "lifecycle_event", "identity_lifecycle_review_queue")}
        c.execute("CHECKPOINT")
    finally:
        c.close()
    # Detect concurrent/upstream changes before publishing the immutable version.
    for name, source in paths.items():
        if file_hash(source) != hashes[name]:
            raise ValueError("source changed during build: " + name)
    manifest = {"schema_version": 1, "provider": "Stock Radar historical-database-v1", "source_version": version,
        "created_at": datetime.now(timezone.utc).isoformat(), "database_sha256": file_hash(path),
        "coverage_start": str(calendar[0]), "coverage_end": str(calendar[1]), "sessions": calendar[2],
        "coverage_complete": False, "scope": rules["scope"], "counts": counts,
        "inputs": {n: {"path": str(p.resolve()), "sha256": hashes[n]} for n, p in paths.items()},
        "notes": ["No original source/store/master changed", "A/B/C is audit only", "Absent population evidence remains unknown",
                  "Primary/secondary directories are sampled observations, not full-market legal attestations",
                  "Raw prices are homogeneous; legacy split basis is diagnostic and never spliced",
                  "Legacy event publication dates unavailable: retrospective facts only; terminal economics disabled"]}
    (directory / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (root / "data/pit/construction/current.json").write_text(json.dumps({"directory": str(directory.resolve()), "source_version": version},
                                                                          ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"directory": str(directory), "counts": counts, "source_version": version}, indent=2), flush=True)
    return directory


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path.cwd())
    args = p.parse_args()
    build(args.root.resolve())

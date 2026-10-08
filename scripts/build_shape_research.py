"""Local-only shape sanity pipeline, window census and immutable derived store.

Run: python -B scripts/build_shape_research.py --root .
All source databases are attached READ_ONLY. No network, QC or strategy run.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path

import duckdb
import pandas as pd
import yaml

from radar.pit.builder import digest
from radar.pit.features import file_hash


def lit(value):
    return "'" + str(value).replace("'", "''") + "'"


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def build(root):
    root = Path(root).resolve()
    pointer = read(root / "data/pit/construction/current.json")
    parent = Path(pointer["directory"])
    parent_manifest = read(parent / "manifest.json")
    master = read(root / "data/security-master-manifest.json")
    normalized = root / "data/pit/normalized" / master["source_version"]
    paths = {"historical_database": parent / "historical.duckdb", "historical_manifest": parent / "manifest.json",
             "legacy_ohlcv": normalized / "pit-research.duckdb", "raw_ohlcv": root / "data/pit/research-grade/raw-source.duckdb",
             "raw_manifest": root / "data/pit/research-grade/raw-source.manifest.json",
             "shape_rules": root / "config/shape_research_rules.json", "research_config": root / "config/research.yaml",
             "builder": Path(__file__).resolve(), "adapter": root / "src/radar/pit/shape.py"}
    hashes = {k: file_hash(v) for k, v in paths.items()}
    if hashes["historical_database"] != parent_manifest["database_sha256"]:
        raise ValueError("strict parent bytes changed")
    if hashes["raw_ohlcv"] != read(paths["raw_manifest"])["database_sha256"]:
        raise ValueError("raw source bytes changed")
    rules = read(paths["shape_rules"])
    cfg = yaml.safe_load(paths["research_config"].read_text(encoding="utf-8"))["research"]
    version = digest({"schema_version": 1, "inputs": hashes})
    directory = root / "data/pit/shape-research/versions" / version
    directory.mkdir(parents=True, exist_ok=True)
    output = directory / "shape.duckdb"
    if (directory / "manifest.json").exists():
        if file_hash(output) != read(directory / "manifest.json")["database_sha256"]:
            raise ValueError("published shape store mutated")
        return directory
    if output.exists():
        output.unlink()  # exact unpublished output only
    c = duckdb.connect(str(output))
    now = datetime.now(timezone.utc).isoformat()
    try:
        c.execute("SET threads=4")
        c.execute("SET memory_limit='3GB'")
        for alias, key in (("hist", "historical_database"), ("legacy", "legacy_ohlcv"), ("rawsrc", "raw_ohlcv")):
            c.execute(f"ATTACH {lit(paths[key])} AS {alias} (READ_ONLY)")
        c.execute("CREATE TABLE sessions AS SELECT date,row_number() OVER(ORDER BY date) AS session_no FROM hist.sessions")
        c.execute("CREATE TABLE population AS SELECT * FROM hist.daily_population WHERE security_type='common'")
        c.execute("""CREATE TABLE split_action AS SELECT security_id,effective_date AS date,
            CAST(json_extract(details,'$.to_factor') AS DOUBLE)/CAST(json_extract(details,'$.for_factor') AS DOUBLE) AS factor,
            confidence,evidence_hash FROM hist.lifecycle_event WHERE event_type IN ('split','reverse_split')
            QUALIFY row_number() OVER(PARTITION BY security_id,effective_date ORDER BY confidence='verified' DESC,event_id)=1""")
        c.execute("CREATE TABLE invalid_split_action AS SELECT * FROM split_action WHERE factor IS NULL OR NOT isfinite(factor) OR factor<=0 OR factor>1000")
        c.execute("DELETE FROM split_action WHERE factor IS NULL OR NOT isfinite(factor) OR factor<=0 OR factor>1000")
        print("building single-source OHLCV candidates", flush=True)
        c.execute(f"""CREATE TABLE candidate AS
            SELECT b.security_id,b.symbol,b.date,b.open,b.high,b.low,b.close,CAST(b.volume AS DOUBLE) AS volume,
              'legacy:'||b.provider||':'||b.feed AS source,b.adjustment AS basis,{lit(hashes['legacy_ohlcv'])} AS source_hash,1 AS priority,
              CAST(b.downloaded_at AS VARCHAR) AS retrieved_at
            FROM legacy.daily_bars b JOIN population p ON b.security_id=p.security_id AND b.symbol=p.symbol AND b.date=p.date
            UNION ALL
            SELECT p.security_id,b.symbol,b.date,b.open,b.high,b.low,b.close,CAST(b.volume AS DOUBLE),
              'Dolt:post-no-preference/stocks',b.adjustment,{lit(hashes['raw_ohlcv'])},3,CAST(b.downloaded_at AS VARCHAR)
            FROM rawsrc.daily_bars b JOIN population p ON b.symbol=p.symbol AND b.date=p.date
            UNION ALL
            SELECT b.security_id,b.symbol,b.date,b.open,b.high,b.low,b.close,CAST(b.volume AS DOUBLE),
              b.source,b.basis,b.source_database_sha256,2,b.retrieved_at
            FROM hist.accepted_price b JOIN population p ON b.security_id=p.security_id AND b.symbol=p.symbol AND b.date=p.date
            WHERE NOT EXISTS (SELECT 1 FROM rawsrc.daily_bars r WHERE r.symbol=b.symbol AND r.date=b.date)
        """)
        c.execute("""CREATE TABLE ordered AS SELECT b.*,b.security_id||'|'||b.source||'|'||b.basis AS series_id,
            p.membership_status,p.boundary_violation,p.eligible,p.latest_primary,p.evidence_conflict,s.session_no,
            lag(b.close) OVER w AS previous_close,lag(b.volume) OVER w AS previous_volume,
            lag(s.session_no) OVER w AS previous_session,coalesce(a.factor,1) AS split_factor,
            a.factor IS NOT NULL AS known_split, a.confidence AS split_evidence_confidence,
            (ib.security_id IS NOT NULL OR ra.security_id IS NOT NULL) AS identity_conflict,
            (ct.security_id IS NOT NULL) AS class_or_name_boundary,
            bad.security_id IS NOT NULL AS invalid_split_action,
            (p.boundary_violation OR (m.listing_date IS NOT NULL AND b.date<m.listing_date)
             OR (m.delisting_date IS NOT NULL AND b.date>m.delisting_date)) AS future_leakage
            FROM candidate b JOIN population p USING(security_id,symbol,date)
            JOIN sessions s USING(date) JOIN hist.ticker_episode m USING(interval_id)
            LEFT JOIN split_action a ON a.security_id=b.security_id AND a.date=b.date
            LEFT JOIN invalid_split_action bad ON bad.security_id=b.security_id AND bad.date=b.date
            LEFT JOIN hist.issuer_conflict_boundary ib ON ib.security_id=b.security_id AND b.date>=ib.conflict_known_on
            LEFT JOIN hist.review_annotation ra ON ra.security_id=b.security_id AND b.date BETWEEN ra.disputed_start AND ra.disputed_end
            LEFT JOIN (SELECT DISTINCT security_id,effective_date FROM hist.lifecycle_event
                WHERE event_type IN ('class_transition','name_change') AND confidence='candidate') ct
                ON ct.security_id=b.security_id AND ct.effective_date=b.date
            WINDOW w AS (PARTITION BY b.security_id,b.source,b.basis ORDER BY b.date)""")
        c.execute("""CREATE TABLE measured AS SELECT *,
            open/previous_close * CASE WHEN basis='raw' THEN split_factor ELSE 1 END AS gap_ratio,
            close/previous_close * CASE WHEN basis='raw' THEN split_factor ELSE 1 END AS return_ratio,
            (NOT (isfinite(open) AND isfinite(high) AND isfinite(low) AND isfinite(close) AND isfinite(volume))
             OR open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL OR volume IS NULL
             OR least(open,high,low,close)<=0 OR volume<0 OR volume<>floor(volume)
             OR high<greatest(open,close,low) OR low>least(open,close)) AS invalid_ohlcv,
            previous_session IS NOT NULL AND session_no-previous_session>1 AS suspicious_gap,
            (volume=0 OR volume/nullif(previous_volume,0)>100 OR volume/nullif(previous_volume,0)<0.01) AS volume_warning
            FROM ordered""")
        c.execute(f"""CREATE TABLE source_conflict AS SELECT DISTINCT a.security_id,a.date
            FROM measured a JOIN measured b ON a.security_id=b.security_id AND a.date=b.date AND a.source<b.source
            WHERE abs((a.close/a.open)/(b.close/b.open)-1)>{rules['source_intraday_ratio_difference']}
             OR abs((a.high/a.low)/(b.high/b.low)-1)>{rules['source_intraday_ratio_difference']}
             OR (a.previous_session=b.previous_session AND abs(a.return_ratio/b.return_ratio-1)>{rules['source_return_relative_difference']})""")
        split_tests = " OR ".join(f"abs(gap_ratio/{factor}-1)<={rules['split_ratio_tolerance']}" for factor in rules["split_like_factors"])
        c.execute(f"""CREATE TABLE findings AS SELECT m.*,
            (gap_ratio>{rules['extreme_ratio_high']} OR gap_ratio<{rules['extreme_ratio_low']}
             OR return_ratio>{rules['extreme_ratio_high']} OR return_ratio<{rules['extreme_ratio_low']}
             OR high/low>{rules['maximum_intraday_high_low_ratio']}) AS extreme_gap,
            ((gap_ratio>{rules['extreme_ratio_high']} OR gap_ratio<{rules['extreme_ratio_low']}) AND ({split_tests})) AS suspected_split,
            sc.security_id IS NOT NULL AS source_conflict,
            basis NOT IN ('raw','split') AS mixed_basis,
            membership_status<>'confirmed_member' OR volume_warning OR (basis='raw' AND known_split AND split_evidence_confidence<>'verified') AS minor_uncertainty
            FROM measured m LEFT JOIN source_conflict sc USING(security_id,date)""")
        c.execute(f"""CREATE TABLE shape_price AS SELECT *,
            CASE WHEN future_leakage OR identity_conflict OR class_or_name_boundary OR invalid_ohlcv OR extreme_gap OR invalid_split_action
                  OR source_conflict OR mixed_basis OR suspicious_gap THEN 'QUARANTINED'
                 WHEN minor_uncertainty THEN 'READY_WITH_MINOR_UNCERTAINTY' ELSE 'READY' END AS shape_research_status,
            NOT (future_leakage OR identity_conflict OR class_or_name_boundary OR invalid_ohlcv OR coalesce(extreme_gap,false) OR invalid_split_action
                  OR source_conflict OR mixed_basis OR suspicious_gap) AS shape_research_ready,
            concat_ws('|', CASE WHEN future_leakage THEN 'future_leakage' END,
                CASE WHEN identity_conflict THEN 'issuer_collision_or_reviewed_ticker_reuse' END,
                CASE WHEN class_or_name_boundary THEN 'class_or_name_boundary' END,
                CASE WHEN invalid_ohlcv THEN 'invalid_ohlcv' END,
                CASE WHEN suspected_split THEN 'unresolved_split_like' END,
                CASE WHEN invalid_split_action THEN 'invalid_split_action' END,
                CASE WHEN extreme_gap AND NOT suspected_split THEN 'major_unexplained_gap' END,
                CASE WHEN source_conflict THEN 'material_source_shape_conflict' END,
                CASE WHEN mixed_basis THEN 'mixed_basis' END,
                CASE WHEN suspicious_gap THEN 'missing_calendar_sessions' END,
                CASE WHEN minor_uncertainty THEN 'noncritical_uncertainty' END) AS shape_research_reason,
            source AS shape_research_source,{lit(now)} AS shape_research_checked_at
            FROM findings""")
        # Nullable first-row ratio flags must not accidentally quarantine all first rows.
        c.execute("UPDATE shape_price SET shape_research_ready=false WHERE shape_research_status='QUARANTINED'")
        c.execute("""CREATE TABLE session_assessment AS SELECT p.*,
            coalesce(b.shape_research_status,'MISSING') AS shape_research_status,
            coalesce(b.shape_research_ready,false) AS shape_research_ready,
            coalesce(b.shape_research_reason,'no_ohlcv') AS shape_research_reason,
            b.source AS shape_research_source,b.basis,b.series_id,b.shape_research_checked_at
            FROM population p LEFT JOIN shape_price b USING(security_id,symbol,date)
            QUALIFY row_number() OVER(PARTITION BY p.security_id,p.date
                ORDER BY b.shape_research_ready DESC NULLS LAST,b.priority,b.source)=1""")
        c.execute("""CREATE TABLE shape_review_queue AS SELECT security_id,symbol,date,source,basis,shape_research_reason,
            identity_conflict,class_or_name_boundary,invalid_ohlcv,extreme_gap,suspected_split,source_conflict,
            mixed_basis,future_leakage,invalid_split_action FROM shape_price
            WHERE identity_conflict OR class_or_name_boundary OR invalid_ohlcv OR extreme_gap OR source_conflict OR mixed_basis OR future_leakage OR invalid_split_action""")
        # Absence is uncertainty, not an asserted delisting. A gap creates a new run;
        # complete rolling windows never bridge it. Do not put benign absence in AI queue.
        c.execute("""CREATE TABLE segmented AS SELECT *,sum(CASE WHEN NOT shape_research_ready OR suspicious_gap THEN 1 ELSE 0 END)
            OVER(PARTITION BY series_id ORDER BY date ROWS UNBOUNDED PRECEDING) AS run_no
            FROM shape_price""")
        c.execute("""CREATE TABLE rolling_base AS SELECT *,
            row_number() OVER(PARTITION BY series_id,run_no ORDER BY date) AS run_row,
            sum(CASE WHEN membership_status NOT IN ('confirmed_member','probable_member') THEN 1 ELSE 0 END)
            OVER(PARTITION BY series_id ORDER BY date ROWS UNBOUNDED PRECEDING) AS unknown_prefix
            FROM segmented""")
        splits = cfg["frozen_splits"]
        assignments = {name: [bounds[0], bounds[1]] for name, bounds in splits.items() if isinstance(bounds, list)}
        latest = str(c.execute("SELECT max(date) FROM sessions").fetchone()[0])
        assignments["fresh_oos"] = [str((pd.Timestamp(splits["fresh_oos_after"]) + pd.Timedelta(days=1)).date()), latest]
        print("counting complete, purged windows", flush=True)
        chunks = []
        for length in rules["windows"]:
            offset = length-1
            query = f"""SELECT security_id,series_id,source,basis,priority,symbol AS historical_ticker,
                membership_status,shape_research_status,date AS decision_date,{length} AS length,
                lag(date,{offset}) OVER w AS window_start,
                lag(session_no,{offset}) OVER w AS start_session,
                lag(run_no,{offset}) OVER w AS start_run,
                lag(shape_research_ready,{offset}) OVER w AS start_ready,
                unknown_prefix-coalesce(lag(unknown_prefix,{length}) OVER w,0)=0 AS supported_membership,
                session_no,run_no,shape_research_ready
                FROM rolling_base WINDOW w AS (PARTITION BY series_id ORDER BY date)"""
            chunks.append(f"SELECT * FROM ({query}) WHERE shape_research_ready AND start_ready AND run_no=start_run AND session_no-start_session={offset}")
        c.execute("CREATE TABLE source_window_index AS " + " UNION ALL ".join(chunks))
        c.execute("""CREATE TABLE universe_window_index AS SELECT * FROM source_window_index
            QUALIFY row_number() OVER(PARTITION BY security_id,decision_date,length ORDER BY supported_membership DESC,priority,source)=1""")
        cases = " ".join(f"WHEN window_start>=DATE {lit(b[0])} AND decision_date<=DATE {lit(b[1])} THEN {lit(name)}" for name,b in assignments.items())
        c.execute(f"""CREATE TABLE visual_window_index AS SELECT *,CASE {cases} END AS split_assignment
            FROM source_window_index WHERE (CASE {cases} END) IS NOT NULL
            QUALIFY row_number() OVER(PARTITION BY security_id,decision_date,length ORDER BY supported_membership DESC,priority,source)=1""")
        c.execute("CREATE INDEX window_lookup ON visual_window_index(security_id,decision_date,length)")
        c.execute("CREATE INDEX universe_lookup ON universe_window_index(decision_date,length)")
        c.execute("CREATE INDEX price_lookup ON shape_price(series_id,date)")
        counts = {name: c.execute("SELECT count(*) FROM " + name).fetchone()[0] for name in
                  ("population","shape_price","session_assessment","shape_review_queue","visual_window_index","universe_window_index")}
        # The public store only needs canonical prices, status, actions and indexes.
        for table in ("candidate","ordered","measured","findings","segmented","rolling_base","source_window_index","source_conflict"):
            c.execute("DROP TABLE " + table)
        c.execute("CHECKPOINT")
    finally:
        c.close()
    # Complete source locks rechecked after the build. No parent promotion.
    after = {k: file_hash(v) for k,v in paths.items()}
    if hashes != after:
        raise ValueError("source changed during shape build")
    manifest = {"schema_version":1,"source_version":version,"created_at":now,"parent_version":pointer["source_version"],
                "database_sha256":file_hash(output),"inputs":{k:{"path":str(paths[k]),"sha256":v} for k,v in hashes.items()},
                "rules":rules,"split_version":cfg["split_version"],"split_assignments":assignments,"counts":counts,
                "scope":"Observed US common equity intervals, not complete US market; independent normalized shape research, never strict acceptance",
                "source_policy":"Single source/basis window; legacy split-adjusted constant scales cancel in normalized input. Raw factors effective<=T only. Missing known_on prevents claiming vendor publication PIT.",
                "strict_sources_unchanged":True,"production_provider_changed":False,"training_performed":False}
    (directory / "manifest.json").write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding="utf-8")
    (root / "data/pit/shape-research/current.json").write_text(json.dumps({"directory":str(directory),"source_version":version},ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"directory":str(directory),"counts":counts},ensure_ascii=False),flush=True)
    return directory


if __name__ == "__main__":
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,default=Path.cwd())
    build(parser.parse_args().root)

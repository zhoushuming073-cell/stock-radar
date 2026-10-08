"""Bound existing local incremental OHLCV; no download or full-store rebuild.

Core Shape store is immutable. A small sidecar supplies existing post-F bars
and decision windows. Same-provider append must pass an overlap comparison.
"""
from datetime import datetime, timezone
import json
from pathlib import Path

import duckdb
import pandas as pd

from radar.pit.builder import digest
from radar.pit.features import file_hash


def lit(x):return "'"+str(x).replace("'","''")+"'"


def build(root):
    root=Path(root).resolve()
    pointer=json.loads((root/'data/pit/shape-research/current.json').read_text(encoding='utf-8'))
    core=Path(pointer['directory']);manifest=json.loads((core/'manifest.json').read_text(encoding='utf-8'))
    paths={'core':core/'shape.duckdb','core_manifest':core/'manifest.json',
           'history':Path(manifest['inputs']['historical_database']['path']),
           'live_bars':root/'data/market.duckdb','contract':root/'config/shape_research_contract_v1.json','builder':Path(__file__)}
    hashes={k:file_hash(v) for k,v in paths.items()}
    if hashes['core']!=manifest['database_sha256']:raise ValueError('core changed')
    version=digest(hashes);out=root/'data/pit/shape-research/fresh-oos'/version;out.mkdir(parents=True,exist_ok=True)
    path=out/'fresh.duckdb'
    if (out/'manifest.json').exists():return out
    if path.exists():raise ValueError('unpublished fresh output requires explicit review, not replacement')
    c=duckdb.connect(str(path))
    try:
        c.execute("SET threads=4")
        c.execute("SET memory_limit='2GB'")
        for alias,key in [('core','core'),('hist','history'),('live','live_bars')]:c.execute('ATTACH '+lit(paths[key])+' AS '+alias+' (READ_ONLY)')
        start=manifest['split_assignments']['fresh_oos'][0]
        rows=c.execute('SELECT date FROM core.sessions WHERE date<? ORDER BY date DESC LIMIT 126',[start]).fetchall()
        lookback=min(x[0] for x in rows)
        # Compare historical overlapping bars, not future returns. Any revision
        # within the 20-session bridge quarantines that issuer's fresh append.
        bridge=c.execute('SELECT date FROM core.sessions WHERE date<? ORDER BY date DESC LIMIT 20',[start]).fetchall()
        bridge_start=min(x[0] for x in bridge)
        c.execute(f"""CREATE TABLE bridge_check AS SELECT s.security_id,count(*) AS overlap_rows,
            bool_or(abs(b.open/s.open-1)>0.000001 OR abs(b.high/s.high-1)>0.000001
             OR abs(b.low/s.low-1)>0.000001 OR abs(b.close/s.close-1)>0.000001 OR b.volume<>s.volume) AS conflict
            FROM core.shape_price s JOIN live.daily_bars b USING(symbol,date)
            WHERE s.source='legacy:alpaca:sip' AND s.basis='split' AND b.provider='alpaca' AND b.feed='sip'
            AND b.adjustment='split' AND s.date>=DATE {lit(bridge_start)} AND s.date<DATE {lit(start)} GROUP BY s.security_id""")
        cols="security_id,symbol,date,open,high,low,close,volume,source,basis,source_hash,shape_research_ready,shape_research_status,membership_status"
        c.execute(f"""CREATE TABLE base_lookback AS SELECT {cols} FROM core.shape_price
            WHERE source='legacy:alpaca:sip' AND basis='split' AND date>=DATE {lit(lookback)} AND date<DATE {lit(start)}""")
        c.execute(f"""CREATE TABLE fresh_candidate AS SELECT p.security_id,b.symbol,b.date,b.open,b.high,b.low,b.close,CAST(b.volume AS DOUBLE) AS volume,
            'legacy:alpaca:sip' AS source,b.adjustment AS basis,{lit(hashes['live_bars'])} AS source_hash,p.membership_status,
            (br.overlap_rows IS NULL OR br.overlap_rows<5 OR br.conflict) AS bridge_conflict,
            (ib.security_id IS NOT NULL OR ra.security_id IS NOT NULL) AS identity_conflict,
            (p.boundary_violation OR m.listing_date IS NOT NULL AND b.date<m.listing_date OR m.delisting_date IS NOT NULL AND b.date>m.delisting_date) AS boundary_conflict,
            NOT (isfinite(b.open) AND isfinite(b.high) AND isfinite(b.low) AND isfinite(b.close) AND isfinite(b.volume))
            OR b.open IS NULL OR b.high IS NULL OR b.low IS NULL OR b.close IS NULL OR b.volume IS NULL
            OR least(b.open,b.high,b.low,b.close)<=0 OR b.volume<0 OR b.volume<>floor(b.volume) OR b.high<greatest(b.open,b.close,b.low) OR b.low>least(b.open,b.close)
            OR ct.security_id IS NOT NULL AS invalid_ohlcv
            FROM live.daily_bars b JOIN core.population p USING(symbol,date)
            JOIN hist.ticker_episode m USING(interval_id)
            LEFT JOIN bridge_check br ON br.security_id=p.security_id
            LEFT JOIN hist.issuer_conflict_boundary ib ON ib.security_id=p.security_id AND b.date>=ib.conflict_known_on
            LEFT JOIN hist.review_annotation ra ON ra.security_id=p.security_id AND b.date BETWEEN ra.disputed_start AND ra.disputed_end
            LEFT JOIN (SELECT DISTINCT security_id,effective_date FROM hist.lifecycle_event WHERE event_type IN ('class_transition','name_change') AND confidence='candidate') ct
              ON ct.security_id=p.security_id AND ct.effective_date=b.date
            WHERE b.date>=DATE {lit(start)} AND b.provider='alpaca' AND b.feed='sip' AND b.adjustment='split'""")
        c.execute("""CREATE TABLE sequence AS SELECT *,lag(close) OVER w AS previous_close,
            lag(date) OVER w AS previous_date FROM (
              SELECT security_id,date,open,high,low,close,volume FROM base_lookback
              UNION ALL SELECT security_id,date,open,high,low,close,volume FROM fresh_candidate)
            WINDOW w AS (PARTITION BY security_id ORDER BY date)""")
        r=manifest['rules']
        c.execute(f"""CREATE TABLE fresh_price AS SELECT f.*,
            (f.open/s.previous_close>{r['extreme_ratio_high']} OR f.open/s.previous_close<{r['extreme_ratio_low']}
              OR f.close/s.previous_close>{r['extreme_ratio_high']} OR f.close/s.previous_close<{r['extreme_ratio_low']}
              OR f.high/f.low>{r['maximum_intraday_high_low_ratio']}) AS extreme_gap,
            NOT (bridge_conflict OR identity_conflict OR boundary_conflict OR invalid_ohlcv
              OR coalesce(f.open/s.previous_close>{r['extreme_ratio_high']} OR f.open/s.previous_close<{r['extreme_ratio_low']}
              OR f.close/s.previous_close>{r['extreme_ratio_high']} OR f.close/s.previous_close<{r['extreme_ratio_low']}
              OR f.high/f.low>{r['maximum_intraday_high_low_ratio']},true)) AS shape_research_ready,
            CASE WHEN bridge_conflict OR identity_conflict OR boundary_conflict OR invalid_ohlcv
              OR coalesce(f.open/s.previous_close>{r['extreme_ratio_high']} OR f.open/s.previous_close<{r['extreme_ratio_low']}
              OR f.close/s.previous_close>{r['extreme_ratio_high']} OR f.close/s.previous_close<{r['extreme_ratio_low']}
              OR f.high/f.low>{r['maximum_intraday_high_low_ratio']},true) THEN 'QUARANTINED'
              WHEN membership_status<>'confirmed_member' OR f.volume=0 THEN 'READY_WITH_MINOR_UNCERTAINTY' ELSE 'READY' END AS shape_research_status
            FROM fresh_candidate f JOIN sequence s USING(security_id,date)""")
        c.execute(f'CREATE TABLE prices AS SELECT {cols} FROM base_lookback UNION ALL SELECT {cols} FROM fresh_price')
        windows=[]
        for length in r['windows']:
            offset=length-1
            windows.append(f"""SELECT * FROM (SELECT security_id,date AS decision_date,{length} AS length,
                lag(date,{offset}) OVER w AS window_start,
                count(*) OVER tail AS row_count,bool_and(shape_research_ready) OVER tail AS safe,
                bool_and(membership_status IN ('confirmed_member','probable_member')) OVER tail AS supported_membership,
                s.session_no-min(s.session_no) OVER tail AS session_span
                FROM prices p JOIN core.sessions s USING(date)
                WINDOW w AS (PARTITION BY security_id ORDER BY date),
                    tail AS (PARTITION BY security_id ORDER BY date ROWS BETWEEN {offset} PRECEDING AND CURRENT ROW))
                WHERE decision_date>=DATE {lit(start)} AND row_count={length} AND session_span={offset} AND safe""")
        c.execute('CREATE TABLE fresh_window_index AS '+' UNION ALL '.join(windows))
        c.execute('CREATE INDEX fresh_lookup ON fresh_window_index(security_id,decision_date,length)')
        stats={name:c.execute('SELECT count(*) FROM '+name).fetchone()[0] for name in ['fresh_price','fresh_window_index','bridge_check']}
        stats['windows']=c.execute('SELECT length,count(*) FILTER(WHERE supported_membership),count(*) FROM fresh_window_index GROUP BY length ORDER BY length').fetchall()
        stats['quarantined_rows']=c.execute('SELECT count(*) FROM fresh_price WHERE NOT shape_research_ready').fetchone()[0]
        stats['bridge_conflict_ids']=c.execute('SELECT count(*) FROM bridge_check WHERE conflict').fetchone()[0]
        for table in ('base_lookback','fresh_candidate','sequence'):c.execute('DROP TABLE '+table)
        c.execute('CHECKPOINT')
    finally:c.close()
    if hashes!={k:file_hash(v) for k,v in paths.items()}:raise ValueError('source changed during local append')
    m={'source_version':version,'database_sha256':file_hash(path),'core_version':pointer['source_version'],
       'created_at':datetime.now(timezone.utc).isoformat(),'fresh_start':start,'policy':'Decision date in Fresh; historical lookback permitted; no outcome/model fitting',
       'inputs':{k:{'path':str(paths[k]),'sha256':v} for k,v in hashes.items()},'counts':stats,'network_downloads':0}
    (out/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8')
    (out.parent/'current.json').write_text(json.dumps({'directory':str(out),'source_version':version},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(m['counts']),flush=True)
    return out


if __name__=='__main__':build(Path.cwd())

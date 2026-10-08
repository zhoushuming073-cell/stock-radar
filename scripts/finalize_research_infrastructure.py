"""Freeze local research policy, recount coverage and historical failure risk.

No strategy evaluation, model training, download or file deletion.
"""
from datetime import datetime, timezone
import json
from pathlib import Path

import duckdb

from radar.pit.features import file_hash
from radar.research.infrastructure import semantic_hash


def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def lit(x):return "'"+str(x).replace("'","''")+"'"
def ratio(n,d):return {'numerator':int(n),'denominator':int(d),'pct':round(100*n/d,4) if d else None}


def finalize(root,tests=None):
    root=Path(root).resolve();sp=read(root/'data/pit/shape-research/current.json');fp=read(root/'data/pit/shape-research/fresh-oos/current.json')
    core=Path(sp['directory']);fresh=Path(fp['directory']);cm=read(core/'manifest.json');fm=read(fresh/'manifest.json')
    contract=read(root/'config/shape_research_contract_v1.json')
    semantics={'version':'research-infrastructure-v1','shape_rule_version':contract['version'],
               'core_database_sha256':file_hash(core/'shape.duckdb'),'fresh_database_sha256':file_hash(fresh/'fresh.duckdb'),
               'contract_semantic_hash':semantic_hash(contract),'membership_policy':contract['membership_policy'],
               'price_basis':contract['price_basis'],'fresh_start':fm['fresh_start'],'fresh_oos_policy':contract['fresh_oos_policy'],
               'frozen_splits':cm['split_assignments'],'visual_dataset_version':'shape-visual-v1-with-fresh-decision-lookback',
               'research_api_code_sha256':file_hash(root/'src/radar/research/infrastructure.py')}
    if semantics['core_database_sha256']!=cm['database_sha256'] or semantics['fresh_database_sha256']!=fm['database_sha256']:raise ValueError('store mutated')
    profile={'version':'Research Infrastructure v1','status':'RESEARCH_INFRASTRUCTURE_V1_FROZEN' if tests else 'PROVISIONAL_PENDING_TESTS',
             'creation_date':datetime.now(timezone.utc).isoformat(),'semantic_hash':semantic_hash(semantics),'semantics':semantics,
             'core_directory':core.relative_to(root).as_posix(),'fresh_directory':fresh.relative_to(root).as_posix(),
             'rules_hash':file_hash(root/'config/shape_research_rules.json'),'contract_file_sha256':file_hash(root/'config/shape_research_contract_v1.json'),
             'source_manifests':[str((core/'manifest.json').relative_to(root)),str((fresh/'manifest.json').relative_to(root))],
             'source_manifest_hashes':[file_hash(core/'manifest.json'),file_hash(fresh/'manifest.json')],
             'tests':tests,'database_expansion':'CLOSED','database_maintenance':'ACTIVE',
             'known_limitations':['Observed common intervals, not complete US history','Fragmented identities and eligibility-unknown missing episodes remain',
                                  'Split candidates lack complete announcement publication PIT','Absolute split prices are not PIT execution prices',
                                  'Previously viewed Test stays exploratory','No pre-2026-09-29 model/parameter freeze is asserted; Fresh data preparation only']}
    (root/'config/research_infrastructure_v1.json').write_text(json.dumps(profile,ensure_ascii=False,indent=2),encoding='utf-8')
    c=duckdb.connect();c.execute("SET threads=4");c.execute("SET memory_limit='2GB'")
    for alias,path in [('core',core/'shape.duckdb'),('fresh',fresh/'fresh.duckdb'),('hist',Path(cm['inputs']['historical_database']['path']))]:
        c.execute('ATTACH '+lit(path)+' AS '+alias+' (READ_ONLY)')
    c.execute("""CREATE TEMP VIEW assessment AS SELECT a.security_id,a.symbol,a.date,a.membership_status,
        coalesce(f.shape_research_status,a.shape_research_status) AS status,
        coalesce(f.shape_research_ready,a.shape_research_ready) AS ready
        FROM core.session_assessment a LEFT JOIN fresh.fresh_price f USING(security_id,date)""")
    scalar=lambda q:c.execute(q).fetchone()[0]
    total=scalar('SELECT count(*) FROM assessment')
    ready=scalar('SELECT count(*) FROM assessment WHERE ready')
    stats={'price':{k:ratio(n,total) for k,n in c.execute('SELECT status,count(*) FROM assessment GROUP BY status').fetchall()},
           'technical_ready':ratio(ready,total),'supported_safe_candles':scalar("SELECT count(*) FROM assessment WHERE ready AND membership_status IN ('confirmed_member','probable_member')"),
           'any_safe_security_ids':scalar('SELECT count(DISTINCT security_id) FROM assessment WHERE ready'),
           'available':ratio(scalar("SELECT count(*) FROM assessment WHERE status<>'MISSING'"),total),
           'fresh_window_counts':fm['counts']['windows'],'fresh_candidate_rows':fm['counts']['fresh_price'],
           'fresh_quarantined_rows':fm['counts']['quarantined_rows'],'fresh_bridge_conflict_ids':fm['counts']['bridge_conflict_ids'],
           'fresh_price_end':str(scalar('SELECT max(date) FROM fresh.fresh_price')),
           'fresh_formal_evaluation':'NOT_RUN; no verified pre-F model/parameter freeze receipt asserted',
           'network_downloads':0,'core_database_unchanged':semantics['core_database_sha256']==cm['database_sha256']}
    windows=c.execute("""SELECT length,split_assignment,count(*) FILTER(WHERE supported_membership) supported,count(*) including_unknown
        FROM core.visual_window_index GROUP BY ALL ORDER BY length,split_assignment""").df().to_dict('records')
    for length,supported,inc in fm['counts']['windows']:
        windows.append({'length':length,'split_assignment':'fresh_oos','supported':supported,'including_unknown':inc})
    stats['visual_windows']=windows
    stats['supported_safe_security_ids']=scalar("SELECT count(DISTINCT security_id) FROM assessment WHERE ready AND membership_status IN ('confirmed_member','probable_member')")
    stats['research_windows']=c.execute('''SELECT length,sum(supported) AS supported,sum(including_unknown) AS including_unknown FROM (
        SELECT length,count(*) FILTER(WHERE supported_membership) AS supported,count(*) AS including_unknown FROM core.universe_window_index GROUP BY length
        UNION ALL SELECT length,count(*) FILTER(WHERE supported_membership),count(*) FROM fresh.fresh_window_index GROUP BY length
        ) GROUP BY length ORDER BY length''').df().to_dict('records')
    stats['latest_supported_universe']=c.execute('''SELECT decision_date::VARCHAR AS decision_date,length,count(*) AS security_ids
        FROM fresh.fresh_window_index WHERE decision_date=(SELECT max(date) FROM fresh.fresh_price) AND supported_membership GROUP BY ALL ORDER BY length''').df().to_dict('records')
    # Potential comes from dated membership, not from already-complete OHLCV.
    # Qualification applies to every common ID first; disappearance is only an
    # audit stratum, never a historical runtime filter.
    r=contract['research_relevant_disappeared'];minimum=r['minimum_supported_potential_sessions']
    c.execute(f"""CREATE TEMP TABLE potential AS WITH membership_rows AS (
        SELECT p.security_id,p.date,s.session_no,s.session_no-row_number() OVER(PARTITION BY security_id ORDER BY date) AS segment
        FROM core.population p JOIN core.sessions s USING(date) WHERE membership_status IN ('confirmed_member','probable_member')),
        numbered AS (SELECT *,row_number() OVER(PARTITION BY security_id,segment ORDER BY date) AS segment_row FROM membership_rows)
        SELECT security_id,min(date) AS potential_date FROM numbered WHERE segment_row>={minimum} GROUP BY security_id""")
    c.execute("""CREATE TEMP TABLE evidence_prices AS SELECT b.security_id,b.date,b.close,b.volume,s.session_no
        FROM core.shape_price b JOIN potential p USING(security_id) JOIN core.sessions s USING(date)
        WHERE NOT invalid_ohlcv AND NOT identity_conflict AND NOT future_leakage AND volume>0
        QUALIFY row_number() OVER(PARTITION BY b.security_id,b.date ORDER BY b.priority)=1""")
    count=r['minimum_priced_observations'];offset=count-1
    c.execute(f"""CREATE TEMP TABLE research_qualified AS WITH liquidity AS (
        SELECT *,count(*) OVER w AS priced_count,median(close*volume) OVER w AS median_dollar_volume,
            session_no-lag(session_no,{offset}) OVER(PARTITION BY security_id ORDER BY date) AS span
        FROM evidence_prices WINDOW w AS (PARTITION BY security_id ORDER BY date ROWS BETWEEN {offset} PRECEDING AND CURRENT ROW))
        SELECT l.security_id,min(l.date) AS qualified_on FROM liquidity l JOIN potential p USING(security_id)
        WHERE l.date>=p.potential_date AND priced_count={count} AND span<20
        AND median_dollar_volume>={r['median_dollar_volume_floor']} AND close>{r['price_floor']} GROUP BY l.security_id""")
    stats['survivorship']={}
    cohorts={'all_observed_disappeared':"q.disappeared AND q.security_type='common'",
             'research_relevant_disappeared':"q.disappeared AND q.security_type='common' AND q.security_id IN (SELECT security_id FROM research_qualified)",
             'potential_but_eligibility_unknown':"q.disappeared AND q.security_type='common' AND q.security_id IN (SELECT security_id FROM potential) AND q.security_id NOT IN (SELECT security_id FROM research_qualified)",
             'known_acquired':"q.security_id IN (SELECT security_id FROM hist.lifecycle_event WHERE event_type='merger' AND confidence='verified')",
             'known_exchange_cessation':"q.security_id IN (SELECT security_id FROM hist.lifecycle_event WHERE event_type='trading_suspension' AND confidence='verified')",
             'known_bankrupt_terminated':"q.security_id IN (SELECT security_id FROM hist.lifecycle_event WHERE event_type IN ('bankruptcy','termination','equity_cancellation') AND confidence='verified')"}
    for name,cond in cohorts.items():
        ids=scalar('SELECT count(*) FROM hist.identity_quality q WHERE '+cond)
        c.execute('CREATE OR REPLACE TEMP VIEW cohort AS SELECT q.security_id FROM hist.identity_quality q WHERE '+cond)
        days=scalar('SELECT count(*) FROM assessment a JOIN cohort USING(security_id)')
        any_available=scalar("SELECT count(DISTINCT a.security_id) FROM assessment a JOIN cohort USING(security_id) WHERE status<>'MISSING'")
        safeids=scalar('SELECT count(DISTINCT a.security_id) FROM assessment a JOIN cohort USING(security_id) WHERE ready')
        record={'total_ids':ids,'available_ohlcv_ids':ratio(any_available,ids),'shape_ready_ids':ratio(safeids,ids),
                'sessions':days,'safe_sessions':ratio(scalar('SELECT count(*) FROM assessment a JOIN cohort USING(security_id) WHERE ready'),days),
                'missing_sessions':ratio(scalar("SELECT count(*) FROM assessment a JOIN cohort USING(security_id) WHERE status='MISSING'"),days),
                'quarantined_sessions':ratio(scalar("SELECT count(*) FROM assessment a JOIN cohort USING(security_id) WHERE status='QUARANTINED'"),days),'windows':{}}
        for length in cm['rules']['windows']:
            n=scalar(f'''SELECT count(DISTINCT w.security_id) FROM (
                SELECT security_id,length,supported_membership FROM core.universe_window_index
                UNION ALL SELECT security_id,length,supported_membership FROM fresh.fresh_window_index
                ) w JOIN cohort USING(security_id) WHERE length={length} AND supported_membership''')
            record['windows'][str(length)]=ratio(n,ids)
        record['missing_date_range']=c.execute("SELECT min(date)::VARCHAR,max(date)::VARCHAR,count(DISTINCT a.security_id) FROM assessment a JOIN cohort USING(security_id) WHERE status='MISSING'").fetchone()
        stats['survivorship'][name]=record
    stats['survivorship_definition']={'rules':r,'not_a_runtime_survival_filter':True,
        'eligibility_unknown_is_not_illiquid':True,'limitations':'Qualification needs some actual price/liquidity evidence; retain independent membership-potential unresolved cohort to avoid a tautologically complete denominator.'}
    stats['research_relevant_missing_by_year']=c.execute("""SELECT year(date),count(*),count(DISTINCT a.security_id) FROM assessment a
        JOIN research_qualified k USING(security_id) JOIN hist.identity_quality q USING(security_id)
        WHERE q.disappeared AND status='MISSING' GROUP BY 1 ORDER BY 1""").fetchall()
    stats['ready_safety']={k:scalar(q) for k,q in {
        'core_future':"SELECT count(*) FROM core.shape_price WHERE shape_research_ready AND future_leakage",
        'core_identity':"SELECT count(*) FROM core.shape_price WHERE shape_research_ready AND identity_conflict",
        'core_split':"SELECT count(*) FROM core.shape_price WHERE shape_research_ready AND (suspected_split OR invalid_split_action)",
        'fresh_boundary':"SELECT count(*) FROM fresh.fresh_price WHERE shape_research_ready AND boundary_conflict",
        'fresh_identity':"SELECT count(*) FROM fresh.fresh_price WHERE shape_research_ready AND identity_conflict",
        'fresh_extreme':"SELECT count(*) FROM fresh.fresh_price WHERE shape_research_ready AND extreme_gap",
        'fresh_bridge':"SELECT count(*) FROM fresh.fresh_price WHERE shape_research_ready AND bridge_conflict"}.items()}
    stats['profile_semantic_hash']=profile['semantic_hash'];stats['contract_semantic_hash']=semantics['contract_semantic_hash']
    stats['core_database_sha256']=semantics['core_database_sha256'];stats['fresh_database_sha256']=semantics['fresh_database_sha256']
    c.close()
    (root/'reports/evidence/research-infrastructure-finalization-2026-10-08.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'ready':stats['technical_ready'],'supported':stats['supported_safe_candles'],'fresh_windows':stats['fresh_window_counts'],
                      'survivorship':stats['survivorship']['research_relevant_disappeared'],'uncertain':stats['survivorship']['potential_but_eligibility_unknown']['total_ids'],
                      'profile_hash':profile['semantic_hash']}),flush=True)
    return profile,stats


if __name__=='__main__':finalize(Path.cwd())

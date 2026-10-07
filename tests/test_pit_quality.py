"""Adversarial coverage population, not invented real-world issuer history."""
import json
from pathlib import Path

import duckdb
import pandas as pd

from radar.lab.universe import LocalSecurityMaster
from radar.pit.quality import coverage_v2, local_scorecard


def test_no_price_denominator_and_dated_secondary_claim_do_not_follow_reused_ticker(tmp_path):
    csv = tmp_path / 'security-master.csv'
    csv.write_text('security_id,symbol,valid_from,valid_to,listing_date,delisting_date,exchange,security_type,eligible,resolution_status,classification_confidence,security_name\n'
                   'OLD,XYZ,2022-10-26,2022-10-27,,,NYSE,common,true,unresolved,inferred,Old common\n'
                   'NEW,XYZ,2022-10-28,2022-10-28,,,NYSE,common,true,unresolved,inferred,New common\n'
                   'U,UNKN,2022-10-26,2022-10-28,,,NASDAQ,unknown,false,unresolved,unresolved,Unknown\n')
    manifest = tmp_path / 'security-master-manifest.json'
    manifest.write_text(json.dumps({'provider':'fixture','source_version':'1','coverage_start':'2022-10-26',
                                   'coverage_end':'2022-10-28','coverage_complete':True}))
    master = LocalSecurityMaster(csv, manifest)
    db = tmp_path / 'prices.duckdb'
    with duckdb.connect(str(db)) as c:
        c.execute('CREATE TABLE daily_bars(date DATE,symbol VARCHAR,security_id VARCHAR,close DOUBLE,volume BIGINT)')
        c.execute("INSERT INTO daily_bars VALUES ('2022-10-26','SPY',NULL,380,100),('2022-10-27','SPY',NULL,380,100),('2022-10-28','SPY',NULL,390,100),('2022-10-28','XYZ','NEW',10,1)")
        c.execute('CREATE TABLE assets(symbol VARCHAR,status VARCHAR)')
        c.execute("INSERT INTO assets VALUES ('XYZ','ACTIVE')")
    secondary = tmp_path / 'claims.csv'
    secondary.write_text('source,symbol,source_delisting_date\ndelisted,XYZ,2022-10-27\n')
    catalog = {'sources':{},'mappings':[],'events':[]}
    report = coverage_v2(master, db, tmp_path/'reports', catalog, secondary=secondary)
    assert report['common']['eligible_common_episodes'] == 2
    assert report['common']['expected_security_sessions'] == 3
    assert report['common']['missing_security_sessions'] == 2
    assert report['common']['no_price'] == 1
    assert report['common']['complete_available_interval'] == 1
    assert len(master.observed_on('2022-10-28')) == 2
    queue = {r['security_id']:r for r in json.loads((tmp_path/'reports/price-priority-queue.json').read_text())}
    assert queue['OLD']['secondary_delist_claim'] is True
    assert queue['OLD']['tier'] == 1
    assert queue['U']['tier'] == 3
    # NEW has complete prices and is absent from the missing-price queue;
    # the old ticker claim still refers only to OLD's two missing sessions.
    assert 'NEW' not in queue
    replay = coverage_v2(master, db, tmp_path/'replay', catalog, secondary=secondary)
    assert replay == report
    assert report['scorecard']['lean_pit_execution_ready'] is False
    cached = tmp_path/'data/pit/reports/1/coverage-v2.json'
    cached.parent.mkdir(parents=True)
    cached.write_text(json.dumps(report))
    assert local_scorecard(master,tmp_path)['coverage_audit_sha256'] == report['semantic_sha256']
    report['scorecard']['lean_pit_execution_ready'] = True
    cached.write_text(json.dumps(report))
    fallback = local_scorecard(master,tmp_path)
    assert fallback['lean_pit_execution_ready'] is False
    assert 'coverage_audit_status' in fallback

import json
from pathlib import Path

import duckdb
import pandas as pd
import pytest

from radar.pit.database import (
    HistoricalDatabase, LIFECYCLE_TYPES, classify_episode, fixed_sample,
    install_review_annotation, membership_truth, validate_intervals,
    validate_prices, validate_review_packet,
)
from radar.pit.features import file_hash


def mapping(sid, symbol, start, end, kind='common'):
    return dict(security_id=sid,symbol=symbol,valid_from=start,valid_to=end,
                security_type=kind,exchange='NASDAQ',eligible=True)


@pytest.fixture
def catalog(tmp_path):
    root = tmp_path/'parent'
    root.mkdir()
    intervals = pd.DataFrame([
        mapping('OLD','REUSE','2024-01-02','2024-01-03'),
        mapping('NEW','REUSE','2024-01-04','2024-01-05'),
        mapping('RENAME','FB','2024-01-02','2024-01-03'),
        mapping('RENAME','META','2024-01-04','2024-01-05'),
        mapping('IPO','IPO','2024-01-04','2024-01-05'),
        mapping('ADR','ADS','2024-01-02','2024-01-05','adr'),
    ])
    for col in ['valid_from','valid_to']:
        intervals[col] = pd.to_datetime(intervals[col]).dt.date
    rows=[]
    for r in intervals.to_dict('records'):
        for day in pd.date_range(r['valid_from'],r['valid_to']):
            rows.append({**r,'date':day.date(),'membership_status':'unknown' if r['security_id']=='ADR' else 'probable_member'})
    frame=pd.DataFrame(rows)
    events=pd.DataFrame([
        {'security_id':'OLD','event_type':'trading_suspension','effective_date':pd.Timestamp('2024-01-04').date(),'confidence':'verified'},
        {'security_id':'IPO','event_type':'listing','effective_date':pd.Timestamp('2024-01-04').date(),'confidence':'verified'},
        {'security_id':'OLD','event_type':'merger','effective_date':pd.Timestamp('2024-01-03').date(),'confidence':'verified'},
        {'security_id':'RENAME','event_type':'exchange_transfer','effective_date':pd.Timestamp('2024-01-04').date(),'confidence':'verified'},
    ])
    with duckdb.connect(str(root/'historical.duckdb')) as c:
        c.register('intervals',intervals);c.execute('CREATE TABLE ticker_episode AS SELECT * FROM intervals')
        c.register('population',frame);c.execute('CREATE TABLE daily_population AS SELECT * FROM population')
        c.execute('CREATE TABLE sessions AS SELECT DISTINCT date FROM daily_population')
        c.register('events',events);c.execute('CREATE TABLE lifecycle_event AS SELECT * FROM events')
        prices=pd.DataFrame([price('OLD','REUSE','2024-01-03'),price('NEW','REUSE','2024-01-04')])
        c.register('price_frame',prices);c.execute('CREATE TABLE accepted_price AS SELECT * FROM price_frame')
    manifest={'schema_version':1,'source_version':'fixture','database_sha256':file_hash(root/'historical.duckdb'),
              'coverage_start':'2024-01-02','coverage_end':'2024-01-05'}
    (root/'manifest.json').write_text(json.dumps(manifest),encoding='utf-8')
    (root/'rules.json').write_text('{}',encoding='utf-8')
    return root,intervals


def price(sid='X',symbol='X',day='2024-01-03',basis='raw'):
    return dict(security_id=sid,symbol=symbol,date=pd.Timestamp(day).date(),open=10.,high=11.,low=9.,close=10.,volume=100,
                source='Dolt',source_version='fixed',retrieved_at='2026-10-08',basis=basis,action_relation='separate',conflict_state='none')


def record(**changes):
    result=dict(cik_count=1,ticker_episode_count=1,type_count=1,material_unresolved=False,disappeared=False,
                official_terminal=False,security_type='common',price_anomaly=False,price_conflict=False,
                cik_observations=2,names_compatible=True,symbol_count=1,exchange_count=1,official_identity=False)
    return {**result,**changes}


def classify(**changes):
    return classify_episode(record(**changes),{'minimum_issuer_observations':2})


def packet(tmp_path, sid='OLD', symbol='REUSE'):
    raw=tmp_path/'raw';raw.mkdir(exist_ok=True)
    (raw/'disclosure.html').write_text('Issuer announces a new common security.',encoding='utf-8')
    return raw,dict(schema_version=1,security_ids=[sid],symbol=symbol,start='2024-01-03',end='2024-01-05',
        disputed_fact='new security despite unchanged ticker',issuer='CIK-0000000001',share_class='common',exchange='NASDAQ',
        lifecycle_result='stock_conversion',confidence='official disclosure; annotation only',classification='C',
        safe_to_merge=False,must_remain_separate=True,evidence=[dict(url='https://issuer.example/disclosure',source_version='2024 release',
            sha256=file_hash(raw/'disclosure.html'),publication_date='2024-01-03',retrieved_at='2026-10-08T00:00:00Z',
            raw_file='disclosure.html',excerpt='Issuer announces a new common security.')])


def test_ticker_reuse_isolation(catalog):
    root,_=catalog
    with HistoricalDatabase(root) as db:
        assert db.population_on('2024-01-03').query("symbol=='REUSE'").security_id.tolist()==['OLD']
        assert db.population_on('2024-01-04').query("symbol=='REUSE'").security_id.tolist()==['NEW']
        assert db.prices('NEW','2024-01-02','2024-01-03').empty


def test_future_ipo_exclusion(catalog):
    with HistoricalDatabase(catalog[0]) as db:
        assert 'IPO' not in set(db.population_on('2024-01-02').security_id)
        assert db.membership_on('IPO','2024-01-02')=='confirmed_non_member'


def test_delisted_history_inclusion(catalog):
    with HistoricalDatabase(catalog[0]) as db:
        assert 'OLD' in set(db.eligible_on('2024-01-03').security_id)
        assert db.membership_on('OLD','2024-01-05')=='confirmed_non_member'
        assert len(db.prices('OLD','2024-01-02','2024-01-05'))==1


def test_rename_continuity(catalog):
    with HistoricalDatabase(catalog[0]) as db:
        assert db.population_on('2024-01-03').query("security_id=='RENAME'").symbol.item()=='FB'
        assert db.population_on('2024-01-04').query("security_id=='RENAME'").symbol.item()=='META'
        assert classify(symbol_count=2,official_identity=True)[0]=='A'


def test_exchange_transfer_has_no_identity_merge():
    assert classify(exchange_count=2)[0]=='B'
    assert classify(exchange_count=2,official_identity=True)[0]=='A'
    assert 'exchange_transfer' in LIFECYCLE_TYPES


def test_merger_lifecycle_is_material(catalog):
    with HistoricalDatabase(catalog[0]) as db:
        assert db.connection.execute("SELECT count(*) FROM lifecycle_event WHERE event_type='merger'").fetchone()[0]==1
    assert classify(material_unresolved=True)[0]=='C'


def test_acquisition_termination_cannot_create_cash():
    assert {'cash_acquisition','termination','stock_conversion'} <= LIFECYCLE_TYPES
    assert classify(disappeared=True,official_terminal=True)[0]=='A'
    assert classify(disappeared=True,official_terminal=False)[0]=='C'


def test_spac_class_transition_never_passes():
    assert classify(type_count=2)[0]=='C'
    assert classify(security_type='spac')[0]=='C'


def test_adr_common_separation(catalog):
    with HistoricalDatabase(catalog[0]) as db:
        assert 'ADR' not in set(db.common_candidates_on('2024-01-02').security_id)
    assert classify(security_type='adr')[0]=='C'


def test_overlapping_ticker_rejected():
    f=pd.DataFrame([mapping('ONE','X','2024-01-02','2024-01-04'),mapping('TWO','X','2024-01-04','2024-01-06')])
    with pytest.raises(ValueError,match='overlapping'):
        validate_intervals(f)


def test_overlapping_security_id_rejected():
    f=pd.DataFrame([mapping('ONE','X','2024-01-02','2024-01-04'),mapping('ONE','Y','2024-01-03','2024-01-06')])
    with pytest.raises(ValueError,match='overlapping'):
        validate_intervals(f)


def test_membership_three_value_logic():
    assert membership_truth('confirmed_member') is True
    assert membership_truth('probable_member') is True
    assert membership_truth('confirmed_non_member') is False
    assert membership_truth('unknown') is None


def test_unknown_is_not_false(catalog):
    with HistoricalDatabase(catalog[0]) as db:
        f=db.population_on('2024-01-02')
        assert pd.isna(f.loc[f.security_id=='ADR','member'].item())
        assert db.membership_on('unobserved','2024-01-02')=='unknown'


def test_random_survivorship_audit_reproducible():
    ids=[f'ID-{i}' for i in range(100)]
    assert fixed_sample(ids,50,'fixed')==fixed_sample(reversed(ids),50,'fixed')
    assert len(fixed_sample(ids,50,'fixed'))==50
    assert fixed_sample(ids,50,'other')!=fixed_sample(ids,50,'fixed')
    assert len(fixed_sample(['A','B'],50,'fixed'))==2


def test_daily_population_sanity(catalog):
    with HistoricalDatabase(catalog[0]) as db:
        for day in ['2024-01-02','2024-01-03','2024-01-04','2024-01-05']:
            f=db.population_on(day)
            assert not f.duplicated(['symbol','date']).any()
            assert not f.duplicated(['security_id','date']).any()
        with pytest.raises(ValueError,match='outside'):
            db.population_on('2023-12-29')


def test_identity_evidence_install_copy_on_write(catalog,tmp_path):
    root,intervals=catalog;raw,p=packet(tmp_path)
    parent_hash=file_hash(root/'historical.duckdb')
    child=install_review_annotation(root,p,raw,tmp_path/'versions')
    assert child!=root and parent_hash==file_hash(root/'historical.duckdb')
    with HistoricalDatabase(child) as db:
        assert db.connection.execute('SELECT count(*) FROM review_annotation').fetchone()[0]==1
        assert db.connection.execute('SELECT count(*) FROM ticker_episode').fetchone()[0]==len(intervals)
        assert db.connection.execute("SELECT security_id FROM daily_population WHERE symbol='REUSE' AND date='2024-01-04'").fetchone()[0]=='NEW'


def test_ai_evidence_cannot_directly_splice(catalog,tmp_path):
    raw,p=packet(tmp_path);p['safe_to_merge']=True
    with pytest.raises(ValueError,match='cannot splice'):
        validate_review_packet(p,raw,catalog[1])


def test_evidence_hash_mismatch_rejected(catalog,tmp_path):
    raw,p=packet(tmp_path);(raw/'disclosure.html').write_text('mutated')
    with pytest.raises(ValueError,match='mismatch'):
        validate_review_packet(p,raw,catalog[1])


def test_fabricated_excerpt_rejected(catalog,tmp_path):
    raw,p=packet(tmp_path);p['evidence'][0]['excerpt']='same security forever'
    with pytest.raises(ValueError,match='unsupported'):
        validate_review_packet(p,raw,catalog[1])


def test_price_provenance_required():
    f=pd.DataFrame([price()]);validate_prices(f)
    with pytest.raises(ValueError,match='provenance'):
        validate_prices(f.drop(columns='source_version'))


def test_no_mixed_adjustment_basis():
    with pytest.raises(ValueError,match='mixed'):
        validate_prices(pd.DataFrame([price(day='2024-01-02'),price(day='2024-01-03',basis='split')]))


@pytest.mark.parametrize('field,value',[('volume',1.5),('open',float('inf')),('low',0),('close',99)])
def test_invalid_raw_prices_rejected(field,value):
    r=price();r[field]=value
    with pytest.raises(ValueError,match='invalid'):
        validate_prices(pd.DataFrame([r]))


def test_native_feature_identity_adapter(catalog):
    with HistoricalDatabase(catalog[0]) as db:
        good=pd.DataFrame([dict(security_id='RENAME',symbol='META',date='2024-01-04',feature=42)])
        assert db.filter_frame(good).feature.item()==42
        good['security_id']='OLD'
        with pytest.raises(ValueError,match='outside'):
            db.filter_frame(good)


def test_documented_conflict_blocks_feature_splice(catalog,tmp_path):
    raw,p=packet(tmp_path,sid='RENAME',symbol='META')
    child=install_review_annotation(catalog[0],p,raw,tmp_path/'versions')
    with HistoricalDatabase(child) as db:
        with pytest.raises(ValueError,match='discontinuity'):
            db.filter_frame(pd.DataFrame([dict(security_id='RENAME',symbol='META',date='2024-01-04')]))


def test_future_review_data_not_used_to_filter_past(catalog,tmp_path):
    raw,p=packet(tmp_path,sid='RENAME',symbol='META');p['start']='2024-01-04'
    child=install_review_annotation(catalog[0],p,raw,tmp_path/'versions')
    with HistoricalDatabase(child) as db:
        assert len(db.filter_frame(pd.DataFrame([dict(security_id='RENAME',symbol='FB',date='2024-01-03')])))==1


def test_database_mutation_rejected(catalog):
    root,_=catalog
    with duckdb.connect(str(root/'historical.duckdb')) as c:
        c.execute('CREATE TABLE corrupt(x INTEGER)')
    with pytest.raises(ValueError,match='mutated'):
        HistoricalDatabase(root)


def test_known_by_session_issuer_conflict_rejected(catalog):
    root,_=catalog
    with duckdb.connect(str(root/'historical.duckdb')) as c:
        c.execute("CREATE TABLE issuer_evidence(security_id VARCHAR,cik VARCHAR,available_on DATE)")
        c.execute("INSERT INTO issuer_evidence VALUES ('RENAME','0000000001','2024-01-02'),('RENAME','0000000002','2024-01-04')")
    path=root/'manifest.json';v=json.loads(path.read_text());v['database_sha256']=file_hash(root/'historical.duckdb');path.write_text(json.dumps(v))
    with HistoricalDatabase(root) as db:
        assert len(db.filter_frame(pd.DataFrame([dict(security_id='RENAME',symbol='FB',date='2024-01-03')])))==1
        with pytest.raises(ValueError,match='issuer conflict known'):
            db.filter_frame(pd.DataFrame([dict(security_id='RENAME',symbol='META',date='2024-01-04')]))


def test_reversed_dates_rejected():
    with pytest.raises(ValueError,match='invalid'):
        validate_intervals(pd.DataFrame([mapping('X','X','2024-01-05','2024-01-02')]))


def test_price_reader_rejects_adjusted_series(catalog):
    with HistoricalDatabase(catalog[0]) as db:
        with pytest.raises(ValueError,match='homogeneous raw'):
            db.prices('OLD','2024-01-02','2024-01-05',basis='split')


def test_coverage_gap_rejected(catalog):
    with HistoricalDatabase(catalog[0]) as db:
        db.validate_coverage(['2024-01-02','2024-01-05'])
        with pytest.raises(ValueError,match='coverage gap'):
            db.validate_coverage(['2024-01-06'])


def test_disappearance_uncertainty_remains_in_candidate_population(catalog):
    root,_=catalog
    with duckdb.connect(str(root/'historical.duckdb')) as c:
        c.execute("DELETE FROM lifecycle_event WHERE security_id='OLD'")
    path=root/'manifest.json';v=json.loads(path.read_text());v['database_sha256']=file_hash(root/'historical.duckdb');path.write_text(json.dumps(v))
    with HistoricalDatabase(root) as db:
        unknown=db.uncertainty_on('2024-01-04')
        assert unknown.security_id.tolist()==['OLD']
        assert pd.isna(unknown.member.item())
        assert 'OLD' in set(db.candidate_population_on('2024-01-04').security_id)
        assert 'NEW' not in set(db.candidate_population_on('2024-01-02').security_id)


def supplement_module():
    import importlib.util
    spec=importlib.util.spec_from_file_location('database_supplement',Path(__file__).parents[1]/'scripts/supplement_pit_database_prices.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    return module


def test_price_supplement_cache_keys_include_requested_symbols(tmp_path,monkeypatch):
    import datetime
    module=supplement_module();calls=[]
    class Response:
        status_code=200
        def __init__(self,params):self.content=json.dumps({'bars':{params['symbols']:[]}}).encode()
        def json(self):return json.loads(self.content)
    def get(url,params,**kwargs):calls.append(params);return Response(params)
    monkeypatch.setattr(module,'credentials',lambda root:('test-key','test-secret'))
    monkeypatch.setattr(module.requests,'get',get)
    day=datetime.date(2023,5,2)
    first,r1=module.capture(tmp_path,'BBBY',day,day,day)
    second,r2=module.capture(tmp_path,'BBBY',day,day,day,benchmarks=True)
    assert len(calls)==2 and calls[0]['symbols']=='BBBY' and calls[1]['symbols']=='SPY,QQQ'
    assert r1['raw_sha256']!=r2['raw_sha256']
    module.capture(tmp_path,'BBBY',day,day,day)
    assert len(calls)==2


def test_incomplete_price_source_pagination_rejected():
    with pytest.raises(ValueError,match='incomplete'):
        supplement_module().normalize({'next_page_token':'more','bars':{}},'BBBY',{},'OLD')


def test_supplement_historical_asof_and_no_splice(catalog):
    root,_=catalog
    with duckdb.connect(str(root/'historical.duckdb')) as c:
        c.execute("ALTER TABLE ticker_episode ADD COLUMN resolution_status VARCHAR DEFAULT 'verified'")
        c.execute('CREATE TABLE observed_price(security_id VARCHAR)')
    path=root/'manifest.json';v=json.loads(path.read_text());v['database_sha256']=file_hash(root/'historical.duckdb');path.write_text(json.dumps(v))
    module=supplement_module()
    with HistoricalDatabase(root) as db:
        frame=pd.DataFrame([price('OLD','REUSE','2024-01-03')])
        with pytest.raises(ValueError,match='asof outside verified'):
            module.validate_scope(db,frame,pd.Timestamp('2024-01-05').date())
        with pytest.raises(ValueError,match='no splice'):
            module.validate_scope(db,frame,pd.Timestamp('2024-01-03').date())

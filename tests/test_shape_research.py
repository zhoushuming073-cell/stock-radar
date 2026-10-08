"""Real bulk-pipeline fixtures plus causal window/model input contracts."""
import importlib.util
import json
from pathlib import Path
import shutil

import duckdb
import numpy as np
import pandas as pd
import pytest

from radar.pit.database import membership_truth
from radar.pit.features import file_hash
from radar.pit.shape import (ShapeResearchDatabase, assert_training_split, canonical_hash,
                            classify_bar, normalize_window, render_svg, split_for_window, tensor)


ROOT=Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    root=tmp_path_factory.mktemp("shape")
    parent=root/"data/pit/construction/versions/parent"
    parent.mkdir(parents=True)
    (root/"config").mkdir()
    (root/"src/radar/pit").mkdir(parents=True)
    shutil.copyfile(ROOT/"src/radar/pit/shape.py",root/"src/radar/pit/shape.py")
    shutil.copyfile(ROOT/"config/shape_research_rules.json",root/"config/shape_research_rules.json")
    days=pd.bdate_range("2021-09-01",periods=620)
    dates=lambda i:str(days[i].date())
    import yaml
    cfg={"research":{"split_version":"research-splits-v1","frozen_splits":{
        "train":[dates(0),dates(219),dates(229)],"validation":[dates(240),dates(419),dates(429)],
        "test":[dates(430),dates(599),dates(609)],"fresh_oos_after":dates(609)}}}
    (root/"config/research.yaml").write_text(yaml.safe_dump(cfg),encoding="utf8")
    (root/"data/security-master-manifest.json").write_text(json.dumps({"source_version":"fixture"}),encoding="utf8")
    (root/"data/pit/construction/current.json").write_text(json.dumps({"directory":str(parent),"source_version":"parent"}),encoding="utf8")
    pops=[];masters=[];bars=[];raw=[]
    specifications={"S":(0,619),"BAD":(0,619),"J":(0,619),"K":(0,619),"NV":(0,619),"C":(0,619),
                    "F":(0,619),"D":(0,119),"U":(0,619),"V":(0,619),"X":(0,619),
                    "OLD":(0,199),"NEW":(240,619)}
    for sid,(lo,hi) in specifications.items():
        symbol="REUSE" if sid in ("OLD","NEW") else sid
        masters.append({"security_id":sid,"symbol":symbol,"interval_id":sid,"listing_date":days[40].date() if sid=="F" else None,"delisting_date":days[119].date() if sid=="D" else None})
        for i in range(lo,hi+1):
            pops.append({"security_id":sid,"symbol":symbol,"date":days[i].date(),"security_type":"common","interval_id":sid,
                         "membership_status":"unknown" if sid=="U" else "confirmed_member","boundary_violation":False,
                         "eligible":True,"latest_primary":days[i].date(),"evidence_conflict":sid=="U"})
            price=10*(2 if sid=="J" and i>=30 else 1)
            b={"security_id":sid,"symbol":symbol,"date":days[i].date(),"open":price,"high":price+1,"low":price-1,
               "close":price,"volume":0 if sid=="V" and i==30 else 100.,"provider":"fixture","feed":"sip","adjustment":"split","downloaded_at":"2026-10-08"}
            if sid=="BAD" and i==30:b["high"]=5
            if sid=="K":
                b["adjustment"]="raw"
                if i>=30:
                    for col in ["open","high","low","close"]:b[col]/=2
                    b["volume"]*=2
                raw.append({k:v for k,v in b.items() if k!="security_id"})
            else:bars.append(b)
            if sid=="X":
                other={k:v for k,v in b.items() if k!="security_id"}
                other.update(close=15.,high=16.,adjustment="raw",provider="Dolt")
                raw.append(other)
    c=duckdb.connect(str(parent/"historical.duckdb"))
    for name,frame in [("daily_population",pd.DataFrame(pops)),("ticker_episode",pd.DataFrame(masters)),("sessions",pd.DataFrame({"date":days.date}))]:
        c.register("f",frame);c.execute(f"create table {name} as select * from f");c.unregister("f")
    c.execute("create table lifecycle_event(security_id varchar,event_type varchar,effective_date date,confidence varchar,details varchar,evidence_hash varchar,event_id varchar)")
    for sid in ("K","NV"):
        c.execute("insert into lifecycle_event values (?,'split',?,'verified',?,'hash',?)",[sid,days[30].date(),json.dumps({"to_factor":2,"for_factor":1}),sid])
    c.execute("create table issuer_conflict_boundary(security_id varchar,conflict_known_on date)")
    c.execute("insert into issuer_conflict_boundary values ('C',?)",[days[30].date()])
    c.execute("create table review_annotation(security_id varchar,disputed_start date,disputed_end date)")
    c.execute("create table accepted_price(security_id varchar,symbol varchar,date date,open double,high double,low double,close double,volume double,source varchar,basis varchar,source_database_sha256 varchar,retrieved_at varchar)")
    c.close()
    original=file_hash(parent/"historical.duckdb")
    (parent/"manifest.json").write_text(json.dumps({"database_sha256":original}),encoding="utf8")
    normalized=root/"data/pit/normalized/fixture";normalized.mkdir(parents=True)
    rdir=root/"data/pit/research-grade";rdir.mkdir(parents=True)
    for path,frame in [(normalized/"pit-research.duckdb",pd.DataFrame(bars)),(rdir/"raw-source.duckdb",pd.DataFrame(raw))]:
        c=duckdb.connect(str(path));c.register("f",frame);c.execute("create table daily_bars as select * from f");c.close()
    (rdir/"raw-source.manifest.json").write_text(json.dumps({"database_sha256":file_hash(rdir/"raw-source.duckdb")}),encoding="utf8")
    spec=importlib.util.spec_from_file_location("build_shape_research",ROOT/"scripts/build_shape_research.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    directory=module.build(root)
    return root,directory,days,original


@pytest.fixture
def db(built):
    with ShapeResearchDatabase(built[1]) as value:yield value


def row(db,sid,day):
    return db.connection.execute("select * from session_assessment where security_id=? and date=?",[sid,day.date()]).df().iloc[0]


def test_stable_autopass(db,built):
    assert row(db,"S",built[2][30]).shape_research_status=="READY"
    assert "S" in set(db.universe_on(built[2][150]).security_id)


def test_strict_accepted_unchanged(built):
    assert file_hash(built[0]/"data/pit/construction/versions/parent/historical.duckdb")==built[3]
    assert json.loads((built[0]/"data/pit/construction/current.json").read_text())["source_version"]=="parent"


def test_invalid_ohlc_bulk_quarantine(db,built):
    assert row(db,"BAD",built[2][30]).shape_research_status=="QUARANTINED"


def test_split_like_jump_bulk_quarantine(db,built):
    r=row(db,"J",built[2][30]);assert r.shape_research_status=="QUARANTINED"
    assert "unresolved_split_like" in r.shape_research_reason


@pytest.mark.parametrize("sid",["K","NV"])
def test_known_split_no_double_adjustment(db,built,sid):
    assert row(db,sid,built[2][30]).shape_research_ready
    w=db.window(sid,built[2][50],40)
    assert w.normalized.close.nunique()==1


def test_ticker_reuse_never_spliced(db,built):
    assert db.window("OLD",built[2][150],126).metadata["historical_ticker"]=="REUSE"
    with pytest.raises(ValueError):db.window("NEW",built[2][250],40)
    assert "OLD" not in set(db.universe_on(built[2][380]).security_id)


def test_issuer_collision_boundary(db,built):
    assert row(db,"C",built[2][29]).shape_research_ready
    assert not row(db,"C",built[2][30]).shape_research_ready


def test_future_ipo_excluded(db,built):
    assert not row(db,"F",built[2][39]).shape_research_ready
    assert row(db,"F",built[2][40]).shape_research_ready
    assert "F" not in set(db.universe_on(built[2][50],20).security_id)


def test_delisted_history_retained(db,built):
    assert db.window("D",built[2][110],60).metadata["security_id"]=="D"
    assert "D" not in set(db.universe_on(built[2][130],20).security_id)


def test_feature_window_no_future_and_scanner_embargo(db,built):
    f=db.feature_window("S",built[2][230],126)
    assert f.index.max()==built[2][230] and len(f)==126
    assert not any("label" in str(c) for c in f)


def test_strategy2_existing_formulas_and_future_benchmark_isolation(db,built):
    from radar.features.strategy2 import compute_strategy2_features
    days=built[2]; benchmark=pd.Series(np.arange(len(days))+100.,index=days)
    day=days[150]
    a=db.strategy2_feature_window("S",day,benchmark,benchmark)
    changed=benchmark.copy();changed.loc[changed.index>day]=99999999.
    b=db.strategy2_feature_window("S",day,changed,changed)
    pd.testing.assert_frame_equal(a,b)
    window=db.window("S",day,126)
    expected=compute_strategy2_features(window.normalized.set_index("date"),benchmark,benchmark)
    assert a.iloc[-1].ma20_slope_5==expected.iloc[-1].ma20_slope_5
    assert a.index.names==["date","symbol"]
    assert 'avg_dollar_volume_20' not in a


def test_visual_no_future(db,built):
    w=db.window("S",built[2][150],126)
    assert w.ohlcv.date.max()==built[2][150]
    with pytest.raises(ValueError):normalize_window(w.ohlcv,built[2][149])


def test_deterministic_chart_and_hash(db,built):
    a=db.window("S",built[2][150],126);b=db.window("S",built[2][150],126)
    assert render_svg(a.normalized)==render_svg(b.normalized)
    assert a.metadata["ohlcv_hash"]==b.metadata["ohlcv_hash"]
    assert b"REUSE" not in render_svg(a.normalized)


def test_deterministic_tensor_and_future_scale_cancellation(db,built):
    w=db.window("S",built[2][150],126);a=w.ohlcv.copy()
    a[["open","high","low","close"]]*=100
    a.volume/=100
    assert np.array_equal(tensor(normalize_window(a,built[2][150])),tensor(w.normalized))
    assert w.training_tensor().tobytes()==tensor(w.normalized).tobytes()


def test_no_cross_split_input_overlap(db,built):
    for split,(start,end) in db.manifest["split_assignments"].items():
        n=db.connection.execute("select count(*) from visual_window_index where split_assignment=? and (window_start<? or decision_date>?)",[split,start,end]).fetchone()[0]
        assert n==0
    assert db.connection.execute("select count(*) from visual_window_index where security_id='S' and split_assignment='validation' and window_start<?",[built[2][240].date()]).fetchone()[0]==0
    with pytest.raises(ValueError):db.window("S",built[2][245],20)


def test_fresh_oos_protected(db,built):
    with pytest.raises(ValueError):assert_training_split("fresh_oos")
    with pytest.raises(ValueError):db.window("S",built[2][619],20)
    assert db.window("S",built[2][590],20).metadata["split_assignment"]=="test"
    with pytest.raises(ValueError):db.window("S",built[2][590],20).training_tensor()


def test_mixed_adjustment_rejected(db,built):
    w=db.window("S",built[2][150],20);w.ohlcv.loc[0,"basis"]="raw"
    with pytest.raises(ValueError):normalize_window(w.ohlcv,built[2][150])


def test_unknown_not_false(db,built):
    r=row(db,"U",built[2][150]);assert membership_truth(r.membership_status) is None
    assert r.shape_research_status=="READY_WITH_MINOR_UNCERTAINTY"
    assert "U" not in set(db.universe_on(built[2][150]).security_id)
    assert "U" in set(db.universe_on(built[2][150],include_unknown=True).security_id)


def test_material_source_conflict(db,built):
    assert row(db,"X",built[2][30]).shape_research_status=="QUARANTINED"


def test_queue_only_material(db):
    ids=set(db.connection.execute("select distinct security_id from shape_review_queue").df().security_id)
    assert {"S","U","V","D","OLD","NEW"}.isdisjoint(ids)
    assert {"C","BAD","J","X","F"}<=ids


def test_isolated_bad_row_does_not_ban_whole_security(db,built):
    assert db.window("BAD",built[2][100],60).metadata["security_id"]=="BAD"
    with pytest.raises(ValueError):db.window("BAD",built[2][50],40)


def test_bad_first_row_not_allowed_in_window_index(db,built):
    assert db.connection.execute("select count(*) from universe_window_index where security_id='BAD' and decision_date=? and length=20",[built[2][49].date()]).fetchone()[0]==0


def test_future_action_not_used(db,built):
    w=db.window("S",built[2][150],20);a=[{"date":"2099-01-01","factor":10}]
    raw=w.ohlcv.assign(basis="raw")
    assert canonical_hash(normalize_window(raw,built[2][150],a))==canonical_hash(normalize_window(raw,built[2][150]))


@pytest.mark.parametrize("input,status",[
    ({"available":False},"MISSING"),({"invalid_ohlcv":True},"QUARANTINED"),
    ({"membership_status":"confirmed_member"},"READY"),({"membership_status":"unknown"},"READY_WITH_MINOR_UNCERTAINTY")])
def test_classification(input,status):
    assert classify_bar(input)[0]==status


def test_split_assignment_requires_full_containment():
    splits={"train":["2021-01-01","2021-12-31"],"test":["2022-01-15","2022-12-31"]}
    assert split_for_window("2021-12-31","2022-01-20",splits) is None

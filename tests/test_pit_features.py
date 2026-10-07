"""Price identity and Scanner regressions across reused tickers."""
from datetime import date
import json

import duckdb
import pandas as pd
import pytest

from radar.lab.data import load_strategy_segment
from radar.lab.scanner import build_labels, evaluation_settings
from radar.lab.universe import LocalSecurityMaster
from radar.pit.features import build_features
from radar.schema import ensure_schema


def fixture(tmp_path):
    csv = tmp_path / "security-master.csv"
    csv.write_text("security_id,symbol,valid_from,valid_to,listing_date,delisting_date,exchange,security_type,eligible\n"
                   "OLD-SEC,XYZ,2022-01-01,2022-01-03,2022-01-01,2022-01-03,NYSE,common,true\n"
                   "NEW-SEC,XYZ,2022-01-05,2022-01-07,2022-01-05,,NYSE,common,true\n", encoding="utf-8")
    import hashlib
    manifest = tmp_path / "security-master-manifest.json"
    manifest.write_text(json.dumps({"provider": "synthetic", "source_version": "1", "coverage_start": "2022-01-01",
        "coverage_end": "2022-01-07", "coverage_complete": False, "source_attested_completeness": False,
        "reconstruction_kind": "snapshot-interval-v1", "coverage_windows": [["2022-01-01", "2022-01-07"]],
        "output_sha256": hashlib.sha256(csv.read_bytes()).hexdigest()}))
    source = tmp_path / "original.duckdb"
    with duckdb.connect(str(source)) as c:
        ensure_schema(c)
        for day in pd.date_range("2022-01-01", "2022-01-07"):
            for symbol in ("SPY", "QQQ", "XYZ"):
                value = 10. if day.day <= 3 else 100.
                c.execute("INSERT INTO daily_bars VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", [symbol, day.date(),
                    value, value + 1, value - 1, value, 1000, value, 10, "fixture", "sip", "split", day.to_pydatetime()])
    config = tmp_path / "research.yaml"
    config.write_text("""elasticity:
  history_window: 126
  history_min: 40
  burst_quantile: 0.75
  hit_5_weight: 0.7
  hit_10_weight: 0.3
  weights: {beta: 0.15, atr: 0.20, idio: 0.20, burst: 0.25, hit_rate: 0.20}
tradability:
  min_price: 2
  min_avg_dollar_volume_20: 1000000
  min_history_sessions: 126
""")
    return LocalSecurityMaster(csv, manifest), source, config


def test_reused_ticker_feature_history_resets_and_original_prices_remain_readable(tmp_path):
    master, source, config = fixture(tmp_path)
    from radar.pit.features import file_hash
    before = file_hash(source)
    manifest = build_features(source, master, config, tmp_path / "pit.duckdb")
    assert file_hash(source) == before
    assert manifest["counts"]["securities"] == 2
    with duckdb.connect(str(tmp_path / "pit.duckdb"), read_only=True) as c:
        row = c.execute("SELECT security_id,ret_1 FROM daily_features WHERE symbol='XYZ' AND date='2022-01-05'").fetchone()
        assert row == ("NEW-SEC", None)
        assert c.execute("SELECT COUNT(*) FROM daily_bars WHERE symbol='XYZ' AND date='2022-01-04'").fetchone()[0] == 0
    (tmp_path / "security-master-feature-store.json").write_text(json.dumps(manifest))
    bound = LocalSecurityMaster(master.csv_path, master.manifest_path)
    frame = load_strategy_segment(source, pd.Timestamp("2022-01-05"), pd.Timestamp("2022-01-06"), {"ret_1"}, bound)
    assert set(frame.security_id) == {"NEW-SEC"}
    assert pd.isna(frame.loc[(pd.Timestamp("2022-01-05"), "XYZ"), "ret_1"])
    # Queued runs cannot consume altered feature bytes under an unchanged pin.
    with duckdb.connect(str(tmp_path / "pit.duckdb")) as c:
        c.execute("UPDATE daily_features SET ret_1=99 WHERE symbol='XYZ'")
    with pytest.raises(ValueError, match="changed after"):
        load_strategy_segment(source, pd.Timestamp("2022-01-05"), pd.Timestamp("2022-01-06"), {"ret_1"}, bound)


def test_reconstructed_universe_refuses_survivor_features_without_bound_pit_store(tmp_path):
    master, source, _ = fixture(tmp_path)
    with pytest.raises(ValueError, match="identity-bounded"):
        load_strategy_segment(source, pd.Timestamp("2022-01-01"), pd.Timestamp("2022-01-03"), {"ret_1"}, master)


def test_old_security_forward_outcome_cannot_inherit_reused_ticker_prices(tmp_path):
    master, source, _ = fixture(tmp_path)
    with duckdb.connect(str(source), read_only=True) as c:
        bars = c.execute("SELECT date,symbol,open,high,low,close FROM daily_bars WHERE symbol='XYZ'").df()
    mapped = master.filter_frame(bars).reset_index(drop=True)
    mapped["symbol"] = mapped.security_id
    result = build_labels(pd.DataFrame({"signal_date": [pd.Timestamp("2022-01-03")], "symbol": ["OLD-SEC"]}),
                          mapped, pd.date_range("2022-01-01", "2022-01-07"),
                          evaluation_settings({"horizon_sessions": 2}), {"OLD-SEC": pd.Timestamp("2022-01-03")})
    assert result.iloc[0].label_status == "censored"
    assert result.iloc[0].label is None


def test_pit_forward_prices_and_warmup_use_the_bound_identity_store(tmp_path):
    from radar.lab.data import load_forward_bars
    master,source,config=fixture(tmp_path)
    manifest=build_features(source,master,config,tmp_path/'pit.duckdb')
    (tmp_path/'security-master-feature-store.json').write_text(json.dumps(manifest))
    master=LocalSecurityMaster(master.csv_path,master.manifest_path)
    bars=load_forward_bars(source,pd.Timestamp('2022-01-03'),pd.Timestamp('2022-01-06'),master)
    assert set(bars.security_id)=={'OLD-SEC','NEW-SEC'}
    assert pd.Timestamp('2022-01-04') not in set(bars.date)
    frame=load_strategy_segment(source,pd.Timestamp('2022-01-05'),pd.Timestamp('2022-01-06'),{'ret_1'},master)
    assert list(frame.pit_history_sessions)==[1,2]
    assert frame.security_id.eq('NEW-SEC').all()


def test_feature_reuse_refuses_a_changed_identity_mapping(tmp_path):
    from radar.pit.features import rebind_identical_features
    master,source,config=fixture(tmp_path)
    manifest=build_features(source,master,config,tmp_path/'pit.duckdb')
    (tmp_path/'security-master-feature-store.json').write_text(json.dumps(manifest))
    old=LocalSecurityMaster(master.csv_path,master.manifest_path)
    new=LocalSecurityMaster(master.csv_path,master.manifest_path)
    assert rebind_identical_features(old,new,config)['database_sha256']==manifest['database_sha256']
    new.frame.loc[new.frame.security_id.eq('NEW-SEC'),'security_id']='REUSED-ISSUER'
    with pytest.raises(ValueError,match='input mapping differs'):rebind_identical_features(old,new,config)

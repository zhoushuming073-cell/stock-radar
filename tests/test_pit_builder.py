"""Adversarial source histories, not claims about real market completeness."""
from datetime import date
import json

import pandas as pd
import pytest

from radar.lab.universe import LocalSecurityMaster, load_universe
from radar.pit.builder import classify, load_identity_evidence, reconstruct, write_build
from radar.pit.sources import Snapshot, effective_day


def snapshot(day, *, extra=(), removed=(), names=None, errors=()):
    records = [{"symbol": f"S{i:02d}", "name": f"Issuer {i} Common Stock",
                "exchange": ["NASDAQ", "NYSE", "AMEX"][i % 3]} for i in range(30)]
    records = [r for r in records if r["symbol"] not in removed]
    records += list(extra)
    for r in records:
        r.update((names or {}).get(r["symbol"], {}))
    return Snapshot(date.fromisoformat(day), day.replace("-", "") * 5,
                    day + "T12:00:00+00:00", tuple(records), {"file": day}, tuple(errors))


def build(tmp_path, snaps, *, end="2022-01-12", evidence=None, stale=2):
    start, end = date(2022, 1, 1), date.fromisoformat(end)
    frame, report = reconstruct(snaps, start, end, max_stale_days=stale,
                                identity_evidence=evidence)
    manifest = write_build(tmp_path, frame, report, start=start, end=end,
                           source_pins={}, stock_radar_commit="fixture", max_stale_days=stale,
                           identity_evidence=evidence)
    folder = tmp_path / manifest["source_version"]
    return LocalSecurityMaster(folder / "security-master.csv", folder / "security-master-manifest.json"), report


def test_future_listing_and_disappearance_are_membership_not_ipo_or_delisting(tmp_path):
    extra = {"symbol": "NEW", "name": "New Common Stock", "exchange": "NYSE"}
    master, _ = build(tmp_path, [snapshot("2022-01-01"), snapshot("2022-01-02", extra=[extra]),
                                snapshot("2022-01-03", removed=["S00"])])
    assert "NEW" not in set(master.eligible_on("2022-01-01").symbol)
    assert "NEW" in set(master.eligible_on("2022-01-02").symbol)
    assert "S00" in set(master.eligible_on("2022-01-02").symbol)
    assert "S00" not in set(master.eligible_on("2022-01-03").symbol)
    assert master.frame.listing_date.isna().all()
    assert master.frame.delisting_date.isna().all()


def test_reappearance_and_name_change_do_not_guess_identity_merge(tmp_path):
    master, _ = build(tmp_path, [snapshot("2022-01-01"), snapshot("2022-01-02", removed=["S00"]),
                                snapshot("2022-01-03"),
                                snapshot("2022-01-04", names={"S00": {"name": "Different Common Stock"}})])
    ids = [master.eligible_on(day).set_index("symbol").loc["S00", "security_id"]
           for day in ("2022-01-01", "2022-01-03", "2022-01-04")]
    assert len(set(ids)) == 3


def test_exchange_change_keeps_episode_identity_and_historical_exchange(tmp_path):
    master, _ = build(tmp_path, [snapshot("2022-01-01"),
                                snapshot("2022-01-02", names={"S00": {"exchange": "NYSE"}})])
    old = master.eligible_on("2022-01-01").set_index("symbol").loc["S00"]
    new = master.eligible_on("2022-01-02").set_index("symbol").loc["S00"]
    assert old.security_id == new.security_id
    assert (old.exchange, new.exchange) == ("NASDAQ", "NYSE")


def test_verified_identity_name_scope_cannot_swallow_reused_ticker(tmp_path):
    evidence = [{"symbol": "S00", "security_id": "VERIFIED-ISSUER-0", "valid_from": "2022-01-01",
                 "valid_to": "2022-01-12", "resolution_status": "verified",
                 "identity_resolution_method": "dated_notice+class_confirmation",
                 "observed_name_pattern": "Issuer 0", "evidence_url": "https://example.org/notice"}]
    master, _ = build(tmp_path, [snapshot("2022-01-01"),
                   snapshot("2022-01-02", names={"S00": {"name": "Unrelated Common Stock"}})], evidence=evidence)
    original = master.eligible_on("2022-01-01").set_index("symbol").loc["S00"]
    reused = master.eligible_on("2022-01-02").set_index("symbol").loc["S00"]
    assert original.security_id == "VERIFIED-ISSUER-0"
    assert reused.security_id != original.security_id
    assert reused.resolution_status == "unresolved"


def test_verified_dated_rename_continuity(tmp_path):
    evidence = [{"symbol": symbol, "security_id": "SECURITY-1", "valid_from": first,
                 "valid_to": last, "resolution_status": "verified",
                 "identity_resolution_method": "dated_exchange_notice+class_confirmation",
                 "evidence_url": "https://example.org/notice"}
                for symbol, first, last in [("S00", "2022-01-01", "2022-01-01"),
                                           ("NEW", "2022-01-02", "2022-01-12")]]
    master, _ = build(tmp_path, [snapshot("2022-01-01"), snapshot("2022-01-02", removed=["S00"],
                   extra=[{"symbol": "NEW", "name": "Issuer 0 Common Stock", "exchange": "NASDAQ"}])],
                      evidence=evidence)
    assert set(master.frame.loc[master.frame.symbol.isin(["S00", "NEW"]), "security_id"]) == {"SECURITY-1"}


def test_source_gap_and_failed_snapshot_cannot_be_forward_filled(tmp_path):
    master, report = build(tmp_path, [snapshot("2022-01-01"), snapshot("2022-01-02", errors=["NYSE unavailable"]),
                                     snapshot("2022-01-08")])
    assert report["source_gaps"]
    assert len(report["anomalies"]) == 1
    with pytest.raises(ValueError, match="source gap"):
        master.eligible_on("2022-01-02")
    with pytest.raises(ValueError, match="source gap"):
        master.validate_coverage(pd.DatetimeIndex(["2022-01-05"]))
    assert master.eligible_on("2022-01-08").shape[0] == 30


def test_brief_missing_snapshot_uses_bounded_carry(tmp_path):
    master, report = build(tmp_path, [snapshot("2022-01-01"), snapshot("2022-01-03")])
    assert len(master.eligible_on("2022-01-02")) == 30
    assert "2022-01-02" in report["missing_snapshot_dates"]
    with pytest.raises(ValueError, match="source gap"):
        master.eligible_on("2022-01-06")


def test_mass_disappearance_rejected_not_called_delisting(tmp_path):
    master, report = build(tmp_path, [snapshot("2022-01-01"), snapshot("2022-01-02", removed=[f"S{i:02d}" for i in range(20)])])
    assert len(report["anomalies"]) == 1
    with pytest.raises(ValueError, match="source gap"):
        master.eligible_on("2022-01-02")


@pytest.mark.parametrize("record,expected", [
    ({"security_type": "common"}, "common"), ({"ETF": "Y", "name": "X Common Stock"}, "etf"),
    ({"Test Issue": "Y"}, "test"), ({"Test Issue": "Y", "security_type": "common"}, "test"),
    ({"name": "Issuer American Depositary Shares"}, "adr"),
    ({"name": "Issuer Preferred Stock"}, "preferred"), ({"name": "Issuer Warrants"}, "warrant"),
    ({"name": "Issuer Units"}, "unit"), ({"name": "Issuer Rights"}, "rights"),
    ({"name": "Issuer exchange traded notes"}, "etn"), ({"name": "Issuer closed-end fund"}, "closed_end_fund"),
    ({"industry": "Blank Checks", "name": "Issuer Common Stock"}, "spac"),
    ({"name": "Unclassified issuer"}, "unknown"),
])
def test_instrument_types_are_explicit_and_unknown_is_not_common(record, expected):
    assert classify(record)[0] == expected


def test_unknown_types_retained_in_observed_master_but_ineligible(tmp_path):
    master, _ = build(tmp_path, [snapshot("2022-01-01", names={"S00": {"name": "Unclassified issuer"}})])
    assert "S00" in set(master.observed_on("2022-01-01").symbol)
    assert "S00" not in set(master.eligible_on("2022-01-01").symbol)


def test_na_is_a_real_symbol_not_a_missing_value(tmp_path):
    master, _ = build(tmp_path, [snapshot("2022-01-01", extra=[
        {"symbol": "NA", "name": "Issuer Common Stock", "exchange": "NYSE"}])])
    assert "NA" in set(master.eligible_on("2022-01-01").symbol)


def test_nonempty_coverage_is_not_assumed_from_snapshot_file_existence(tmp_path):
    names = {f"S{i:02d}": {"name": "Unclassified issuer"} for i in range(30)}
    master, _ = build(tmp_path, [snapshot("2022-01-01", names=names)])
    with pytest.raises(ValueError, match="no eligible securities"):
        master.validate_coverage(pd.DatetimeIndex(["2022-01-01"]))


def test_deterministic_build_and_future_mutation(tmp_path):
    first = snapshot("2022-01-01")
    master, _ = build(tmp_path, [first])
    again, _ = build(tmp_path, [first])
    assert master.fingerprint == again.fingerprint
    future, _ = build(tmp_path, [first, snapshot("2022-01-08", names={"S00": {"name": "Later issuer"}})])
    pd.testing.assert_frame_equal(master.eligible_on("2022-01-01")[
        ["security_id", "symbol", "exchange", "eligible"]].reset_index(drop=True),
        future.eligible_on("2022-01-01")[["security_id", "symbol", "exchange", "eligible"]].reset_index(drop=True))


def test_source_fingerprint_and_output_mutation_rejection(tmp_path):
    master, _ = build(tmp_path, [snapshot("2022-01-01")])
    manifest = json.loads(master.manifest_path.read_text())
    manifest["source_version"] = "different-source-version"
    master.manifest_path.write_text(json.dumps(manifest))
    changed = LocalSecurityMaster(master.csv_path, master.manifest_path)
    assert master.fingerprint != changed.fingerprint
    master.csv_path.write_text(master.csv_path.read_text().replace("Issuer 0", "Mutation"))
    with pytest.raises(ValueError, match="hash mismatch"):
        LocalSecurityMaster(master.csv_path, master.manifest_path)


def test_fresh_directory_build_and_receipt_time_are_not_universe_identity(tmp_path):
    first, _ = build(tmp_path / "first", [snapshot("2022-01-01")])
    second, _ = build(tmp_path / "second", [snapshot("2022-01-01")])
    assert first.manifest["source_version"] == second.manifest["source_version"]
    assert first.csv_path.read_bytes() == second.csv_path.read_bytes()
    second.manifest["built_at"] = "2099-01-01T00:00:00Z"
    second.manifest["stock_radar_commit"] = "receipt-only"
    second.manifest_path.write_text(json.dumps(second.manifest), encoding="utf-8")
    assert first.fingerprint == LocalSecurityMaster(second.csv_path, second.manifest_path).fingerprint


def test_semantic_feature_identity_keeps_separate_queued_database_byte_gate():
    from radar.lab.universe import semantic_fingerprint, UniverseProvenance, validate_frozen_feature_store
    manifest = {"source_version": "pinned"}
    first = {"database": "a.duckdb", "database_sha256": "a", "source_database_sha256": "input",
             "research_config_sha256": "config", "builder_code_sha256": "code"}
    second = {**first, "database": "b.duckdb", "database_sha256": "b"}
    assert semantic_fingerprint(b"csv", manifest, first) == semantic_fingerprint(b"csv", manifest, second)
    assert semantic_fingerprint(b"csv", manifest, first) != semantic_fingerprint(
        b"csv", manifest, {**second, "research_config_sha256": "changed"})
    provenance = UniverseProvenance("point_in_time", "fixture", "v", "fp", None, None,
                                    "source_dependent", feature_store_sha256="b")
    with pytest.raises(ValueError, match="feature database changed"):
        validate_frozen_feature_store(provenance, {"universe_provenance": {"feature_store_sha256": "a"}})
    validate_frozen_feature_store(provenance, {"universe_provenance": {"feature_store_sha256": "b"}})


def test_duplicate_mapping_rejected_even_when_identity_is_identical(tmp_path):
    master, _ = build(tmp_path, [snapshot("2022-01-01")])
    frame = pd.read_csv(master.csv_path)
    frame = pd.concat([frame, frame.iloc[:1]])
    frame.to_csv(master.csv_path, index=False)
    manifest = json.loads(master.manifest_path.read_text())
    # Exercise the existing certified-import compatibility path too.
    manifest.pop("reconstruction_kind")
    manifest["coverage_complete"] = True
    master.manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="overlapping"):
        LocalSecurityMaster(master.csv_path, master.manifest_path)


def test_identity_mismatch_is_not_silently_remapped(tmp_path):
    master, _ = build(tmp_path, [snapshot("2022-01-01")])
    frame = pd.DataFrame({"date": ["2022-01-01"], "symbol": ["S00"], "security_id": ["WRONG"], "close": [10.]})
    with pytest.raises(ValueError, match="identity differs"):
        master.filter_frame(frame)


def test_current_snapshot_does_not_consume_installed_pit(tmp_path):
    assert load_universe(tmp_path, "current_snapshot", [pd.Timestamp("2022-01-01")])[0] is None


def test_installation_places_all_contract_files_in_data_and_refuses_replacement(tmp_path):
    from pathlib import Path
    import runpy
    install = runpy.run_path(str(Path(__file__).resolve().parents[1] / "scripts/build_pit_universe.py"))["install_build"]
    master, _ = build(tmp_path / "builds", [snapshot("2022-01-01")])
    root = tmp_path / "project"
    with pytest.raises(ValueError, match="build PIT features"):
        install(master.csv_path.parent, root)
    assert not (root / "data/security-master.csv").exists()
    sidecar = {"master_output_sha256": master.manifest["output_sha256"], "feature_basis": "fixture"}
    master.csv_path.with_name("security-master-feature-store.json").write_text(json.dumps(sidecar))
    install(master.csv_path.parent, root)
    installed, _ = load_universe(root, "point_in_time", [pd.Timestamp("2022-01-01")])
    assert installed.feature_store == sidecar
    assert not (root / "security-master-feature-store.json").exists()
    with pytest.raises(ValueError, match="installation refused"):
        install(master.csv_path.parent, root)


def test_available_after_close_is_not_same_day():
    assert str(effective_day("2022-01-03T22:00:00+00:00")) == "2022-01-04"
    assert str(effective_day("2022-01-03T15:00:00+00:00")) == "2022-01-03"


def test_undated_or_conflicting_identity_evidence_rejected(tmp_path):
    p = tmp_path / "evidence.json"
    p.write_text(json.dumps([{"symbol": "AAA", "cik": "0000000001"}]))
    with pytest.raises(ValueError, match="missing"):
        load_identity_evidence(p)

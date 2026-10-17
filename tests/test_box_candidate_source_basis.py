"""The public provenance aggregate must stay bound to verified private chunks."""
from hashlib import sha256
import json

import pytest

from radar.box_labeling.stage_b import digest, packed
from scripts.audit_box_candidate_source_basis import summarize_verified_files


def _fixture(tmp_path):
    folder = tmp_path / "train" / "2022-03-15"
    folder.mkdir(parents=True)
    raw = json.dumps({"payload": {"near_contexts": [
        {"source": "legacy:alpaca:sip", "basis": "split"},
        {"source": "Dolt:stocks", "basis": "raw"}]}}).encode()
    (folder / "0000-of-0001.json").write_bytes(raw)
    verified = {"complete": True, "verify_only": True, "missing_chunks": 0,
                "split": "train", "start": "2022-03-15", "end": "2022-03-15",
                "verified_chunks": 1, "near_lower_union_rows": 2,
                "verified_file_set_sha256": digest(packed([sha256(raw).hexdigest()])),
                "sessions": 1, "eligible_security_days": 2,
                "ri_semantic_hash": "frozen"}
    return tmp_path / "train", verified


def test_verified_source_basis_aggregate(tmp_path):
    folder, verified = _fixture(tmp_path)
    result = summarize_verified_files(folder, "train", "2022-03-15",
                                      "2022-03-15", verified)
    assert result["source_basis_counts"] == [
        {"source": "Dolt:stocks", "basis": "raw", "candidates": 1},
        {"source": "legacy:alpaca:sip", "basis": "split", "candidates": 1}]
    assert result["verified_file_set_sha256"] == verified["verified_file_set_sha256"]
    assert result["daily_distribution"] == {
        "zero_candidate_sessions": 0, "positive_candidate_sessions": 1,
        "positive_min": 2, "positive_median": 2, "positive_max": 2,
        "top_10_candidate_rows": 2}
    assert result["future_ohlcv_values_read"] is False


def test_source_audit_rejects_changed_or_incomplete_file_set(tmp_path):
    folder, verified = _fixture(tmp_path)
    bad = {**verified, "complete": False}
    with pytest.raises(ValueError, match="completely verified"):
        summarize_verified_files(folder, "train", "2022-03-15", "2022-03-15", bad)
    path = folder / "2022-03-15" / "0000-of-0001.json"
    path.write_bytes(path.read_bytes() + b" ")
    with pytest.raises(ValueError, match="file set"):
        summarize_verified_files(folder, "train", "2022-03-15", "2022-03-15", verified)


def test_distribution_preserves_zero_session_and_rejects_missing_day(tmp_path):
    folder = tmp_path / "train"
    raw_zero = json.dumps({"payload": {"near_contexts": []}}).encode()
    raw_one = json.dumps({"payload": {"near_contexts": [
        {"source": "Dolt:stocks", "basis": "raw"}]}}).encode()
    paths = [folder / "2022-03-15" / "0000-of-0001.json",
             folder / "2022-03-16" / "0000-of-0001.json"]
    for path, raw in zip(paths, (raw_zero, raw_one)):
        path.parent.mkdir(parents=True)
        path.write_bytes(raw)
    verified = {"complete": True, "verify_only": True, "missing_chunks": 0,
                "split": "train", "start": "2022-03-15", "end": "2022-03-16",
                "verified_chunks": 2, "near_lower_union_rows": 1,
                "verified_file_set_sha256": digest(packed([
                    sha256(raw).hexdigest() for raw in (raw_zero, raw_one)])),
                "sessions": 2, "eligible_security_days": 1,
                "ri_semantic_hash": "frozen"}
    result = summarize_verified_files(folder, "train", "2022-03-15",
                                      "2022-03-16", verified)
    assert result["daily_distribution"]["zero_candidate_sessions"] == 1
    assert result["daily_distribution"]["positive_candidate_sessions"] == 1
    assert result["daily_distribution"]["top_10_candidate_rows"] == 1
    with pytest.raises(ValueError, match="file set"):
        summarize_verified_files(folder, "train", "2022-03-15",
                                 "2022-03-16", {**verified, "sessions": 3})


def test_all_warmup_sessions_have_no_positive_distribution(tmp_path):
    folder = tmp_path / "train" / "2021-09-01"
    folder.mkdir(parents=True)
    raw = json.dumps({"payload": {"near_contexts": []}}).encode()
    (folder / "0000-of-0001.json").write_bytes(raw)
    verified = {"complete": True, "verify_only": True, "missing_chunks": 0,
                "split": "train", "start": "2021-09-01", "end": "2021-09-01",
                "verified_chunks": 1, "near_lower_union_rows": 0,
                "verified_file_set_sha256": digest(packed([sha256(raw).hexdigest()])),
                "sessions": 1, "eligible_security_days": 0,
                "ri_semantic_hash": "frozen"}
    result = summarize_verified_files(tmp_path / "train", "train",
                                      "2021-09-01", "2021-09-01", verified)
    assert result["daily_distribution"] == {
        "zero_candidate_sessions": 1, "positive_candidate_sessions": 0,
        "positive_min": None, "positive_median": None,
        "positive_max": None, "top_10_candidate_rows": 0}

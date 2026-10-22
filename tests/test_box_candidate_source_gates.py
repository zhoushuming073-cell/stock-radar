"""Source stratification must use the exact sealed candidate population."""
import json
from hashlib import sha256

import pytest

from radar.box_labeling.stage_b import digest, packed
from scripts.summarize_box_candidate_source_gates import source_strata


def fixtures(tmp_path):
    root = tmp_path / "candidates"
    folder = root / "train" / "2024-07-01"
    folder.mkdir(parents=True)
    candidate = folder / "0000-of-0001.json"
    candidate.write_bytes(packed({"payload": {"near_contexts": [
        {"security_id": "A", "source": "legacy:alpaca:sip", "basis": "split"},
        {"security_id": "B", "source": "other", "basis": "raw"}]}}))
    file_set = digest(packed([sha256(candidate.read_bytes()).hexdigest()]))
    base = {"split": "train", "decision_date": "2024-07-01",
            "candidate_file_set_sha256": file_set, "ri_semantic_hash": "RI"}
    issuer = {**base, "official_identity_certified": False, "rows": [
        {"task_id": "2024-07-01:A", "classification": "CONTEMPORANEOUS_ISSUER_ALIAS"},
        {"task_id": "2024-07-01:B", "classification": "OBSERVATIONAL_NO_KNOWN_CONFLICT"}]}
    session = {"same_source_raw_rows": 1, "raw_ready": True,
               "raw_identity_flag": False, "raw_split_flag": False}
    metadata = {**base, "formal_lean_ready": False, "horizon_sessions": 1,
                "rows": [{"task_id": "2024-07-01:A",
                          "complete_horizon_within_split": True,
                          "sessions": [{**session, "same_source_raw_rows": 0}]},
                         {"task_id": "2024-07-01:B",
                          "complete_horizon_within_split": True,
                          "sessions": [session]}]}
    issuer_path, metadata_path = tmp_path / "issuer.json", tmp_path / "metadata.json"
    issuer_path.write_bytes(packed(issuer))
    metadata_path.write_bytes(packed(metadata))
    return root, candidate, issuer_path, metadata_path


def audit_args(tmp_path):
    root, candidate, issuer, metadata = fixtures(tmp_path)
    return (root, issuer, digest(issuer.read_bytes()),
            metadata, digest(metadata.read_bytes())), candidate


def test_separate_source_basis_and_gate_classification(tmp_path):
    args, _ = audit_args(tmp_path)
    result = source_strata(*args)
    assert result["candidates"] == 2
    assert result["source_basis_gate_counts"] == [
        {"source": "legacy:alpaca:sip", "basis": "split",
         "issuer_classification": "CONTEMPORANEOUS_ISSUER_ALIAS",
         "raw_metadata_complete": False, "candidates": 1},
        {"source": "other", "basis": "raw",
         "issuer_classification": "OBSERVATIONAL_NO_KNOWN_CONFLICT",
         "raw_metadata_complete": True, "candidates": 1}]
    assert result["formal_lean_ready"] is False


def test_reject_candidate_file_or_partial_drift(tmp_path):
    args, candidate = audit_args(tmp_path)
    candidate.write_bytes(candidate.read_bytes() + b" ")
    with pytest.raises(ValueError, match="file set differs"):
        source_strata(*args)
    candidate.write_bytes(candidate.read_bytes().rstrip())
    candidate.with_suffix(".partial").write_bytes(b"interrupted")
    with pytest.raises(ValueError, match="partial"):
        source_strata(*args)


def test_reject_candidate_task_mismatch_even_with_matching_file_hash(tmp_path):
    args, candidate = audit_args(tmp_path)
    payload = json.loads(candidate.read_bytes())
    payload["payload"]["near_contexts"][1]["security_id"] = "C"
    candidate.write_bytes(packed(payload))
    file_set = digest(packed([sha256(candidate.read_bytes()).hexdigest()]))
    issuer_path, metadata_path = args[1], args[3]
    for path in (issuer_path, metadata_path):
        data = json.loads(path.read_bytes())
        data["candidate_file_set_sha256"] = file_set
        path.write_bytes(packed(data))
    with pytest.raises(ValueError, match="task sets differ"):
        source_strata(args[0], issuer_path, digest(issuer_path.read_bytes()),
                      metadata_path, digest(metadata_path.read_bytes()))

"""Issuer/raw intersection must bind the same sealed candidate population."""
import json

import pytest

from radar.box_labeling.stage_b import digest
from scripts.summarize_box_candidate_gates import raw_complete, summarize


def test_raw_complete_requires_all_sessions_and_unflagged_same_source_raw():
    row = {"same_source_raw_rows": 1, "raw_ready": True,
           "raw_identity_flag": False, "raw_split_flag": False}
    task = {"complete_horizon_within_split": True, "sessions": [row.copy()]*2}
    assert raw_complete(task, 2)
    assert not raw_complete(task, 3)
    task["sessions"][0]["raw_split_flag"] = True
    assert not raw_complete(task, 2)


def test_intersection_rejects_population_mismatch(tmp_path):
    base = {"split": "train", "decision_date": "2024-07-01",
            "candidate_file_set_sha256": "sealed", "ri_semantic_hash": "RI"}
    issuer = {**base, "official_identity_certified": False,
              "rows": [{"task_id": "A", "classification": "OBSERVATIONAL_NO_KNOWN_CONFLICT"}]}
    metadata = {**base, "formal_lean_ready": False, "horizon_sessions": 1,
                "rows": [{"task_id": "A", "complete_horizon_within_split": True,
                          "sessions": [{"same_source_raw_rows": 1,
                                        "raw_ready": True, "raw_identity_flag": False,
                                        "raw_split_flag": False}]}]}
    a, b = tmp_path / "issuer.json", tmp_path / "metadata.json"
    a.write_text(json.dumps(issuer))
    b.write_text(json.dumps(metadata))
    result = summarize(a, digest(a.read_bytes()), b, digest(b.read_bytes()))
    assert result["classification_by_raw_metadata_complete"] == {
        "OBSERVATIONAL_NO_KNOWN_CONFLICT|raw_complete=true": 1}
    metadata["candidate_file_set_sha256"] = "different"
    b.write_text(json.dumps(metadata))
    with pytest.raises(ValueError, match="populations"):
        summarize(a, digest(a.read_bytes()), b, digest(b.read_bytes()))
    with pytest.raises(ValueError, match="hash mismatch"):
        summarize(a, "wrong", b, digest(b.read_bytes()))

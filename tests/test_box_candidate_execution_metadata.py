"""A metadata audit cannot silently change its sealed candidate population."""
import json

import pytest

from scripts.audit_box_candidate_execution_metadata import candidate_requests


def test_candidate_requests_preserve_source_basis_and_split_end(tmp_path):
    (tmp_path / "0000-of-0001.json").write_text(json.dumps({"payload": {
        "near_contexts": [{"security_id": "A", "source": "S", "basis": "split"},
                          {"security_id": "B", "source": "R", "basis": "raw"}]
    }}))
    requests = candidate_requests(tmp_path, "validation", "2025-06-02")
    assert len(requests) == 2
    assert requests[0] == {"task_id": "2025-06-02:A", "security_id": "A",
                           "decision_date": "2025-06-02", "split": "validation",
                           "split_end": "2025-09-08", "source": "S",
                           "basis": "split"}
    assert requests[1]["basis"] == "raw"


def test_candidate_requests_reject_duplicate_id_across_chunks(tmp_path):
    for index in range(2):
        (tmp_path / f"{index:04d}-of-0002.json").write_text(json.dumps({
            "payload": {"near_contexts": [{"security_id": "A", "source": "S",
                                            "basis": "split"}]}}))
    with pytest.raises(ValueError, match="repeated"):
        candidate_requests(tmp_path, "train", "2024-07-01")

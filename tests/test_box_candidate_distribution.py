import json
from hashlib import sha256

import pytest

from radar.box_labeling.stage_b import digest, packed
from scripts.audit_box_candidate_distribution import audit_split


def fixture(tmp_path, rows):
    folder = tmp_path / "train" / "2024-08-29"
    folder.mkdir(parents=True)
    raw = json.dumps({"payload": {"near_contexts": rows}}).encode()
    (folder / "part.json").write_bytes(raw)
    receipt = {"complete": True, "verify_only": True, "missing_chunks": 0,
               "split": "train", "start": "2024-08-29", "end": "2024-08-29",
               "sessions": 1, "verified_chunks": 1,
               "near_lower_union_rows": len(rows),
               "verified_file_set_sha256": digest(packed([sha256(raw).hexdigest()]))}
    return tmp_path / "train", receipt


def row(sid="OBS-1", day="2024-08-29"):
    return {"security_id": sid, "source": "legacy:alpaca:sip", "basis": "split",
            "detectors": {"quantile-zone-v1": {"decision_date": day}}}


def test_distribution_binds_file_set_and_aggregates(tmp_path):
    folder, verified = fixture(tmp_path, [row(), row("OBS-2")])
    result = audit_split(folder, verified)
    assert result["candidate_days_by_year"] == {"2024": 2}
    assert result["distinct_observed_security_ids"] == 2
    assert result["duplicate_candidate_keys"] == 0
    verified["verified_file_set_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="drift"):
        audit_split(folder, verified)


def test_duplicate_and_bad_date_fail(tmp_path):
    folder, verified = fixture(tmp_path, [row(), row()])
    with pytest.raises(ValueError, match="duplicate"):
        audit_split(folder, verified)
    folder, verified = fixture(tmp_path / "bad", [row(day="2024-08-30")])
    with pytest.raises(ValueError, match="identity/date"):
        audit_split(folder, verified)

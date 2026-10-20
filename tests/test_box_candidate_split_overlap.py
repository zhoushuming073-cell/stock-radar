import json
from hashlib import sha256

import pytest

from radar.box_labeling.stage_b import digest, packed
from scripts.audit_box_candidate_split_overlap import audit_overlap


def sealed(tmp_path, split, day, ids):
    folder = tmp_path / split / day
    folder.mkdir(parents=True)
    rows = [{"security_id": sid, "source": "legacy:alpaca:sip", "basis": "split",
             "detectors": {"quantile-zone-v1": {"decision_date": day}}} for sid in ids]
    raw = json.dumps({"payload": {"near_contexts": rows}}).encode()
    (folder / "part.json").write_bytes(raw)
    receipt = {"complete": True, "verify_only": True, "missing_chunks": 0,
               "split": split, "start": day, "end": day, "sessions": 1,
               "verified_chunks": 1, "near_lower_union_rows": len(rows),
               "verified_file_set_sha256": digest(packed([sha256(raw).hexdigest()]))}
    return tmp_path / split, receipt


def test_shared_observed_id_aggregate(tmp_path):
    train, tr = sealed(tmp_path, "train", "2024-08-29", ["A", "B"])
    validation, va = sealed(tmp_path, "validation", "2024-09-30", ["B", "C"])
    result = audit_overlap(train, validation, tr, va)
    assert result["shared_observed_ids"] == 1
    assert result["train_candidate_days_on_shared_ids"] == 1
    assert result["validation_candidate_days_on_shared_ids"] == 1
    assert result["shared_id_gap_calendar_days"]["min"] == 32


def test_tampered_receipt_and_wrong_split_rejected(tmp_path):
    train, tr = sealed(tmp_path, "train", "2024-08-29", ["A"])
    validation, va = sealed(tmp_path, "validation", "2024-09-30", ["B"])
    tr["verified_file_set_sha256"] = "0" * 64
    with pytest.raises(ValueError, match="drift"):
        audit_overlap(train, validation, tr, va)
    tr["verified_file_set_sha256"] = digest(packed([sha256((train / "2024-08-29" / "part.json").read_bytes()).hexdigest()]))
    with pytest.raises(ValueError, match="order"):
        audit_overlap(validation, train, va, tr)

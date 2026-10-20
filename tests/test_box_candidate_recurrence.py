from datetime import date, timedelta
from hashlib import sha256
import json

import pytest

from radar.box_labeling.stage_b import digest, packed
from scripts.audit_box_candidate_recurrence import audit_recurrence, episode_summary


def test_episode_boundaries_and_repeated_days():
    sessions = [date(2024, 1, 1) + timedelta(days=i) for i in range(24)]
    observed = {"A": [sessions[0], sessions[1], sessions[22]],
                "B": [sessions[23]]}
    assert episode_summary(observed, sessions, 20) == {
        "episodes": 3, "candidate_days_in_multi_day_episodes": 2,
        "largest_episode_candidate_days": 2}
    assert episode_summary(observed, sessions, 21)["episodes"] == 2
    with pytest.raises(ValueError, match="duplicate"):
        episode_summary({"A": [sessions[0], sessions[0]]}, sessions, 20)


def test_sealed_recurrence_and_tamper(tmp_path):
    folder = tmp_path / "train"
    raws = []
    for i in range(3):
        day = f"2024-01-0{i + 2}"
        target = folder / day
        target.mkdir(parents=True)
        rows = [{"security_id": "A", "source": "test", "basis": "raw",
                 "detectors": {"q": {"decision_date": day}}}] if i != 1 else []
        raw = json.dumps({"payload": {"near_contexts": rows}}).encode()
        (target / "part.json").write_bytes(raw)
        raws.append(sha256(raw).hexdigest())
    receipt = {"complete": True, "verify_only": True, "missing_chunks": 0,
               "split": "train", "start": "2024-01-02", "end": "2024-01-04",
               "sessions": 3, "verified_chunks": 3, "near_lower_union_rows": 2,
               "verified_file_set_sha256": digest(packed(raws))}
    result = audit_recurrence(folder, receipt)
    assert result["by_cooldown_sessions"]["20"]["episodes"] == 1
    assert result["by_cooldown_sessions"]["20"]["candidate_days_in_multi_day_episodes"] == 2
    (folder / "2024-01-04" / "part.json").write_text(
        json.dumps({"payload": {"near_contexts": []}}))
    with pytest.raises(ValueError, match="drift"):
        audit_recurrence(folder, receipt)

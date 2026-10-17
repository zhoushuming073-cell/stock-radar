"""A failed receipt preflight must prevent all candidate writes."""
import pytest

from scripts.resume_box_candidate_backfill import resume


ARGS = (None, "train", "2022-01-03", "2022-01-04", None, None, None)


def test_resume_verifies_first_and_only_writes_when_missing(monkeypatch):
    calls = []

    def execute(*args, **kwargs):
        calls.append(kwargs)
        return {"complete": False} if kwargs.get("verify_only") else {"new_chunks": 1}

    monkeypatch.setattr("scripts.resume_box_candidate_backfill.execute", execute)
    result = resume(*ARGS, max_new_chunks=1)
    assert result["run"]["new_chunks"] == 1
    assert calls == [{"verify_only": True}, {"max_new_chunks": 1}]


def test_corrupt_preflight_never_starts_writer(monkeypatch):
    calls = []

    def execute(*args, **kwargs):
        calls.append(kwargs)
        raise ValueError("unexpected or partial candidate artifact")

    monkeypatch.setattr("scripts.resume_box_candidate_backfill.execute", execute)
    with pytest.raises(ValueError, match="unexpected or partial"):
        resume(*ARGS)
    assert calls == [{"verify_only": True}]


def test_complete_preflight_does_not_start_writer(monkeypatch):
    calls = []

    def execute(*args, **kwargs):
        calls.append(kwargs)
        return {"complete": True}

    monkeypatch.setattr("scripts.resume_box_candidate_backfill.execute", execute)
    result = resume(*ARGS)
    assert result["already_complete"] and result["run"] is None
    assert calls == [{"verify_only": True}]

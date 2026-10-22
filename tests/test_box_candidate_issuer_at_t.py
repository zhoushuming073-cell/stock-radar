"""Candidate issuer observations must use the exact T history provenance."""
import pandas as pd
import pytest

from scripts.audit_box_candidate_issuer_at_t import build_windows


class FakeProvider:
    def __init__(self, source="S", basis="split"):
        self.source, self.basis = source, basis

    def history(self, security_id, day, length):
        assert (security_id, day, length) == ("A", "2024-07-01", 126)
        frame = pd.DataFrame({"date": pd.to_datetime(["2024-01-02", day])})
        frame.attrs.update(source=self.source, basis=self.basis)
        return frame


def test_build_windows_uses_asof_t_history_start_and_matching_basis():
    request = {"task_id": "private", "security_id": "A",
               "decision_date": "2024-07-01", "source": "S", "basis": "split"}
    assert build_windows(FakeProvider(), [request]) == [{
        "task_id": "private", "security_id": "A",
        "decision_date": "2024-07-01", "window_start": "2024-01-02"}]
    with pytest.raises(ValueError, match="source or basis drift"):
        build_windows(FakeProvider(basis="raw"), [request])

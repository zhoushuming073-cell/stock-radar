import json

import pytest

from scripts.audit_box_free_event_exposure import parse_scan


def test_event_scan_rejects_incomplete_or_wrong_source():
    data = {"table": "dividend", "events": [
        {"symbol": "ABC", "date": "2025-06-13 00:00:00.000000", "amount": 0.5}],
        "source_version": "pinned", "coverage": ["2023-12-12", "2025-09-22"],
        "receipt": {"status": 200, "error": None}}
    payload = lambda: json.dumps(data).encode()
    parsed, index = parse_scan(payload(), "dividend", "pinned",
                               "2025-05-05", "2025-09-08")
    assert parsed["table"] == "dividend"
    assert len(index[("ABC", "2025-06-13")]) == 1
    for key, value in (("source_version", "other"),
                       ("coverage", ["2025-06-01", "2025-09-22"]),
                       ("error", "truncated")):
        changed = {**data, key: value}
        with pytest.raises(ValueError):
            parse_scan(json.dumps(changed).encode(), "dividend", "pinned",
                       "2025-05-05", "2025-09-08")
    with pytest.raises(ValueError):
        parse_scan(payload(), "split", "pinned", "2025-05-05", "2025-09-08")

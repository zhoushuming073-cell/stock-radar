"""Decision-dated source corroboration must exclude future and stale records."""
from hashlib import sha256
import json

import duckdb
import pytest

from scripts.audit_box_candidate_reference_support import (
    frozen_reference_rules, source_observations, summarize_support,
    support_class,
)


def _issuer(task):
    return {"task_id": task, "cik_count": 1, "full_window_episodes": 1,
            "bad_names": 0, "known_discontinuity": 0,
            "other_active_security_ids": 0}


def test_decision_dated_reference_support_and_freshness():
    with duckdb.connect(":memory:") as c:
        c.execute("""CREATE TABLE ticker_episode (
          security_id VARCHAR, interval_id VARCHAR, valid_from DATE, valid_to DATE)""")
        c.execute("""CREATE TABLE membership_evidence (
          security_id VARCHAR, interval_id VARCHAR, source VARCHAR,
          available_on DATE, name_compatible BOOLEAN, exchange_compatible BOOLEAN)""")
        c.execute("""INSERT INTO ticker_episode VALUES
          ('one','i1','2024-01-01','2025-12-31'),
          ('two','i2','2024-01-01','2025-12-31'),
          ('three','i3','2024-01-01','2025-12-31')""")
        c.execute("""INSERT INTO membership_evidence VALUES
          ('one','i1','cik','2025-01-10',true,true),
          ('one','i1','nasdaq','2025-01-15',true,true),
          ('two','i2','cik','2024-12-01',true,true),
          ('two','i2','nasdaq','2025-01-21',true,true),
          ('three','i3','cik','2025-01-10',true,true),
          ('three','i3','nasdaq','2025-01-10',false,true)""")
        windows = [{"task_id": name, "security_id": name,
                    "window_start": "2024-08-01", "decision_date": "2025-01-20"}
                   for name in ("one", "two", "three")]
        rows = source_observations(c, windows, 31)
    by_task = {row["task_id"]: row for row in rows}
    assert support_class(by_task["one"]) == "BOTH_RECENT_COMPATIBLE"
    assert support_class(by_task["two"]) == "NO_RECENT_COMPATIBLE_REFERENCE"
    assert by_task["two"]["cik_ever_compatible"] is True
    assert by_task["three"]["recent_reference_conflict"] is True
    assert support_class(by_task["three"]) == "CIK_ONLY_RECENT_COMPATIBLE"
    aggregate = summarize_support([_issuer(task) for task in by_task], rows)
    assert aggregate["tasks"] == 3
    assert aggregate["has_older_compatible_cik_but_not_recent"] == 1
    assert aggregate["recent_reference_conflict_tasks"] == 1
    assert sum(aggregate["issuer_observation_by_reference_support"]
               ["OBSERVATIONAL_NO_KNOWN_CONFLICT"].values()) == 3


def test_reference_population_and_freshness_fail_closed():
    with pytest.raises(ValueError, match="populations differ"):
        summarize_support([_issuer("one")], [])
    with duckdb.connect(":memory:") as c:
        with pytest.raises(ValueError, match="freshness"):
            source_observations(c, [], 0)


def test_frozen_rules_accept_checkout_crlf_only(tmp_path):
    root = tmp_path
    config = root / "config"
    core = root / "data/core"
    history = root / "data/construction"
    for folder in (config, core, history):
        folder.mkdir(parents=True)
    rules_path = config / "pit_database_rules.json"
    frozen = b'{"policy":"historical-database-v1",\n"fresh_reference_days":31}\n'
    rules_path.write_bytes(frozen.replace(b"\n", b"\r\n"))
    construction = history / "manifest.json"
    construction.write_text(json.dumps({"database_sha256": "frozen-db", "inputs": {"rules": {
        "sha256": sha256(frozen).hexdigest()}}}), encoding="utf-8")
    (config / "research_infrastructure_v1.json").write_text(
        json.dumps({"core_directory": "data/core"}), encoding="utf-8")
    (core / "manifest.json").write_text(json.dumps({"inputs": {
        "historical_manifest": {"path": str(construction),
                                "sha256": sha256(construction.read_bytes()).hexdigest()},
        "historical_database": {"sha256": "frozen-db"}}}),
        encoding="utf-8")
    rules, digest, _ = frozen_reference_rules(root, rules_path)
    assert rules["fresh_reference_days"] == 31
    assert digest == sha256(frozen).hexdigest()
    checkout = root / "separate-checkout"
    checkout.mkdir()
    copied = checkout / "pit_database_rules.json"
    copied.write_bytes(rules_path.read_bytes())
    assert frozen_reference_rules(root, copied)[1] == digest
    historical = json.loads(construction.read_text(encoding="utf-8"))
    historical["database_sha256"] = "other-db"
    construction.write_text(json.dumps(historical), encoding="utf-8")
    core_manifest = core / "manifest.json"
    reference = json.loads(core_manifest.read_text(encoding="utf-8"))
    reference["inputs"]["historical_manifest"]["sha256"] = sha256(
        construction.read_bytes()).hexdigest()
    core_manifest.write_text(json.dumps(reference), encoding="utf-8")
    with pytest.raises(ValueError, match="database binding"):
        frozen_reference_rules(root, copied)
    historical["database_sha256"] = "frozen-db"
    construction.write_text(json.dumps(historical), encoding="utf-8")
    reference["inputs"]["historical_manifest"]["sha256"] = sha256(
        construction.read_bytes()).hexdigest()
    core_manifest.write_text(json.dumps(reference), encoding="utf-8")
    rules_path.write_bytes(frozen.replace(b"31", b"30"))
    with pytest.raises(ValueError, match="differ from construction"):
        frozen_reference_rules(root, rules_path)

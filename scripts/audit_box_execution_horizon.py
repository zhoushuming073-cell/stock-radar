"""Read-only, split-bounded execution-data *metadata* audit for box diagnostics.

No future OHLCV, outcomes, fills or returns are read. A raw price row is only
an availability observation; the existing PIT dependency closure remains the
sole route to executable LEAN inputs.
"""
from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path

import pandas as pd

from radar.box_labeling.history import BoxHistory
from radar.box_labeling.stage_b import VERSION as SELECTION_VERSION, digest, packed
from scripts.audit_box_execution_preflight import read_frozen

VERSION = "box-execution-horizon-metadata-v1"
HORIZON = 10  # Data-coverage diagnostic only, not a holding-period rule.


def horizon_metadata(connection, requests: list[dict], horizon: int = HORIZON) -> list[dict]:
    """Query session and provenance flags only, bounded by each frozen split."""
    if not 1 <= horizon <= 20:
        raise ValueError("diagnostic horizon must be 1..20 sessions")
    connection.register("box_horizon_request", pd.DataFrame(requests))
    values = connection.execute("""WITH dated AS (
        SELECT b.task_id,b.security_id,b.source,b.basis,s.date,
          row_number() OVER (PARTITION BY b.task_id ORDER BY s.date) AS step
        FROM box_horizon_request b JOIN sessions s
          ON s.date>CAST(b.decision_date AS DATE)
         AND s.date<=CAST(b.split_end AS DATE)
      ), due AS (SELECT * FROM dated WHERE step<=?)
      SELECT d.task_id,d.date,d.step,
        count(p.date) FILTER (WHERE p.source=d.source AND p.basis=d.basis)
          AS matching_rows,
        count(p.date) FILTER (WHERE p.source=d.source AND p.basis='raw')
          AS same_source_raw_rows,
        count(p.date) FILTER (WHERE p.basis='raw') AS any_raw_rows,
        bool_and(p.shape_research_ready) FILTER (
          WHERE p.source=d.source AND p.basis=d.basis) AS matching_ready,
        bool_or(p.identity_conflict OR p.class_or_name_boundary) FILTER (
          WHERE p.source=d.source AND p.basis=d.basis) AS matching_identity_flag,
        bool_or(p.known_split OR p.invalid_split_action OR p.suspected_split) FILTER (
          WHERE p.source=d.source AND p.basis=d.basis) AS matching_split_flag,
        bool_and(p.shape_research_ready) FILTER (
          WHERE p.source=d.source AND p.basis='raw') AS raw_ready,
        bool_or(p.identity_conflict OR p.class_or_name_boundary) FILTER (
          WHERE p.source=d.source AND p.basis='raw') AS raw_identity_flag,
        bool_or(p.known_split OR p.invalid_split_action OR p.suspected_split) FILTER (
          WHERE p.source=d.source AND p.basis='raw') AS raw_split_flag
      FROM due d LEFT JOIN shape_price p
        ON p.security_id=d.security_id AND p.date=d.date
      GROUP BY d.task_id,d.date,d.step ORDER BY d.task_id,d.step""", [horizon]).fetchall()
    columns = ("task_id", "date", "step", "matching_rows", "same_source_raw_rows",
               "any_raw_rows", "matching_ready", "matching_identity_flag",
               "matching_split_flag", "raw_ready", "raw_identity_flag",
               "raw_split_flag")
    return [dict(zip(columns, row)) for row in values]


def classify_session(row: dict) -> tuple[str, ...]:
    issues = []
    if row["matching_rows"] != 1:
        issues.append("missing_or_duplicate_matching_basis")
    elif row["matching_ready"] is not True:
        issues.append("matching_basis_not_research_ready")
    if row["matching_identity_flag"]:
        issues.append("matching_basis_identity_flag")
    if row["matching_split_flag"]:
        issues.append("matching_basis_action_flag")
    if row["same_source_raw_rows"] != 1:
        issues.append("same_source_raw_unavailable_or_ambiguous")
    elif row["raw_ready"] is not True:
        issues.append("same_source_raw_not_research_ready")
    if row["raw_identity_flag"]:
        issues.append("same_source_raw_identity_flag")
    if row["raw_split_flag"]:
        issues.append("same_source_raw_action_flag")
    return tuple(issues)


def summarize(requests: list[dict], metadata: list[dict], horizon: int = HORIZON) -> tuple[list[dict], dict]:
    by_task = defaultdict(list)
    for row in metadata:
        by_task[row["task_id"]].append(row)
    if set(by_task) - {r["task_id"] for r in requests}:
        raise ValueError("unexpected task in horizon query")
    private = []
    for request in requests:
        rows = by_task[request["task_id"]]
        if [r["step"] for r in rows] != list(range(1, len(rows) + 1)):
            raise ValueError("noncontiguous or duplicated horizon session")
        for row in rows:
            row["date"] = str(row["date"])
            row["issues"] = classify_session(row)
        private.append({"task_id": request["task_id"], "security_id": request["security_id"],
                        "decision_date": request["decision_date"], "split": request["split"],
                        "source": request["source"], "basis": request["basis"],
                        "available_sessions_within_split": len(rows),
                        "complete_horizon_within_split": len(rows) == horizon,
                        "sessions": rows})
    issues = Counter(issue for task in private for row in task["sessions"] for issue in row["issues"])
    aggregate = {
        "tasks": len(private), "expected_session_rows": len(private) * horizon,
        "observed_session_rows": sum(len(t["sessions"]) for t in private),
        "split_censored_tasks": sum(not t["complete_horizon_within_split"] for t in private),
        "matching_basis_complete_tasks": sum(t["complete_horizon_within_split"] and
            all(r["matching_rows"] == 1 and r["matching_ready"] is True and
                not r["matching_identity_flag"] and not r["matching_split_flag"]
                for r in t["sessions"]) for t in private),
        "same_source_raw_complete_tasks": sum(t["complete_horizon_within_split"] and
            all(r["same_source_raw_rows"] == 1 and r["raw_ready"] is True and
                not r["raw_identity_flag"] and not r["raw_split_flag"]
                for r in t["sessions"]) for t in private),
        "raw_available_session_rows": sum(r["same_source_raw_rows"] == 1
            for t in private for r in t["sessions"]),
        "any_raw_session_rows": sum(r["any_raw_rows"] > 0
            for t in private for r in t["sessions"]),
        "issues": dict(sorted(issues.items())),
    }
    return private, aggregate


def audit(research_root: Path, selection_path: Path, selection_sha256: str,
          preflight_path: Path, preflight_sha256: str, output_path: Path) -> dict:
    if output_path.exists():
        raise FileExistsError("private horizon receipt already exists")
    selection = read_frozen(selection_path, selection_sha256)
    preflight = read_frozen(preflight_path, preflight_sha256)
    if (selection.get("version") != SELECTION_VERSION
            or selection.get("selection_precedes_detector") is not True
            or len(selection.get("rows", [])) != 48
            or preflight.get("version") != "box-execution-metadata-preflight-v1"
            or preflight.get("selection_sha256") != selection_sha256
            or preflight.get("future_prices_read") is not False
            or preflight.get("future_outcomes_read") is not False
            or preflight.get("formal_lean_ready") is not False):
        raise ValueError("frozen selection/preflight contract mismatch")
    selected = {r["task_id"]: r for r in selection["rows"]}
    if len(selected) != 48 or len(preflight["rows"]) != 43:
        raise ValueError("duplicate or missing frozen diagnostic tasks")
    splits = {"train": ("2021-09-01", "2024-08-29"),
              "validation": ("2024-09-30", "2025-09-08")}
    requests = []
    for prior in preflight["rows"]:
        original = selected.get(prior["task_id"])
        if original is None or original["split"] not in splits:
            raise ValueError("unknown or forbidden split/task")
        if not splits[original["split"]][0] <= original["decision_date"] <= splits[original["split"]][1]:
            raise ValueError("decision outside frozen Train/Validation")
        if prior["issues"] or prior["next_session"] is None:
            raise ValueError("T+1 metadata gate changed")
        if prior["source"] != original["source"] or prior["basis"] != original["basis"]:
            raise ValueError("source/basis mismatch")
        requests.append({"task_id": prior["task_id"], "security_id": original["security_id"],
                         "decision_date": original["decision_date"], "split": original["split"],
                         "split_end": splits[original["split"]][1],
                         "source": original["source"], "basis": original["basis"]})
    if len({r["task_id"] for r in requests}) != 43:
        raise ValueError("duplicate diagnostic task")
    with BoxHistory(research_root) as provider:
        if provider.semantic_hash != selection["ri_semantic_hash"] or (provider.api.profile[
                "semantics"]["frozen_splits"]["train"] != list(splits["train"]) or
                provider.api.profile["semantics"]["frozen_splits"]["validation"] != list(splits["validation"])):
            raise ValueError("RI v1 semantic/split drift")
        metadata = horizon_metadata(provider.api.core.connection, requests)
    rows, aggregate = summarize(requests, metadata)
    first_session = {r["task_id"]: r["sessions"][0]["date"] for r in rows if r["sessions"]}
    for prior in preflight["rows"]:
        day = first_session.get(prior["task_id"])
        if day is not None and day != prior["next_session"]:
            raise ValueError("T+1 session drift from frozen preflight")
        if day is None and prior["next_session"] <= splits[selected[prior["task_id"]]["split"]][1]:
            raise ValueError("unexpected missing in-split T+1 session")
    private = {"version": VERSION, "selection_sha256": selection_sha256,
               "preflight_sha256": preflight_sha256,
               "ri_semantic_hash": selection["ri_semantic_hash"],
               "horizon_sessions": HORIZON, "future_prices_read": False,
               "future_outcomes_read": False, "formal_lean_ready": False,
               "rows": rows}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw = packed(private)
    output_path.write_bytes(raw)
    return {"version": VERSION, "selection_sha256": selection_sha256,
            "preflight_sha256": preflight_sha256,
            "private_receipt_sha256": digest(raw), "horizon_sessions": HORIZON,
            **aggregate, "future_prices_read": False, "future_outcomes_read": False,
            "formal_lean_ready": False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--research-root", type=Path, required=True)
    p.add_argument("--selection", type=Path, required=True)
    p.add_argument("--selection-sha256", required=True)
    p.add_argument("--preflight", type=Path, required=True)
    p.add_argument("--preflight-sha256", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(audit(a.research_root, a.selection, a.selection_sha256,
                           a.preflight, a.preflight_sha256, a.output),
                     ensure_ascii=False, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

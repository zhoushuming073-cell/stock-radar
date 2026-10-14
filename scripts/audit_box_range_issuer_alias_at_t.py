"""Read-only, decision-dated issuer-alias audit for the frozen box sample.

This is an observational cross-check, not an official identity certification or
a causal security-master replacement. Public stdout contains aggregate counts.
"""
from __future__ import annotations

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path

import duckdb
import pandas as pd

from radar.box_labeling.history import BoxHistory
from radar.box_labeling.stage_b import VERSION, digest, packed


def construction_source(research_root: Path) -> tuple[Path, str]:
    profile = json.loads((research_root / "config/research_infrastructure_v1.json").read_text(
        encoding="utf-8"))
    manifest = json.loads((research_root / profile["core_directory"] / "manifest.json").read_text(
        encoding="utf-8"))
    source = manifest["inputs"]["historical_database"]
    path = Path(source["path"])
    hasher = sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b""):
            hasher.update(chunk)
    if hasher.hexdigest() != source["sha256"]:
        raise ValueError("frozen construction database hash drift")
    return path, source["sha256"]


def dated_evidence(connection: duckdb.DuckDBPyConnection,
                   selected: list[dict]) -> list[dict]:
    connection.register("selected_box", pd.DataFrame(selected))
    rows = connection.execute("""WITH episode AS (
        SELECT s.task_id,count(DISTINCT t.interval_id) AS full_window_episodes
        FROM selected_box s LEFT JOIN ticker_episode t
          ON t.security_id=s.security_id
          AND t.valid_from<=CAST(s.window_start AS DATE)
          AND t.valid_to>=CAST(s.decision_date AS DATE)
        GROUP BY s.task_id
      ), own AS (
        SELECT s.task_id, count(DISTINCT e.cik) AS cik_count,
          count(*) FILTER (WHERE e.name_compatible IS FALSE) AS bad_names,
          min(e.cik) AS cik
        FROM selected_box s LEFT JOIN ticker_episode t
          ON t.security_id=s.security_id
          AND t.valid_from<=CAST(s.window_start AS DATE)
          AND t.valid_to>=CAST(s.decision_date AS DATE)
        LEFT JOIN issuer_evidence e
          ON e.security_id=s.security_id AND e.interval_id=t.interval_id
          AND CAST(e.available_on AS DATE)<=CAST(s.decision_date AS DATE)
        GROUP BY s.task_id
      ), aliases AS (
        SELECT s.task_id,
          count(DISTINCT t.security_id) FILTER (
            WHERE t.security_id<>s.security_id) AS other_active_security_ids
        FROM selected_box s JOIN own o USING(task_id)
        LEFT JOIN issuer_evidence e ON e.cik=o.cik
          AND CAST(e.available_on AS DATE)<=CAST(s.decision_date AS DATE)
        LEFT JOIN ticker_episode t ON t.security_id=e.security_id
          AND t.interval_id=e.interval_id
          AND t.valid_from<=CAST(s.decision_date AS DATE)
          AND t.valid_to>=CAST(s.decision_date AS DATE)
        GROUP BY s.task_id
      ), reviewed AS (
        SELECT s.task_id,count(DISTINCT a.security_id) AS known_discontinuity
        FROM selected_box s LEFT JOIN review_annotation a
          ON a.security_id=s.security_id
          AND a.known_on<=CAST(s.decision_date AS DATE)
          AND CAST(s.decision_date AS DATE)
            BETWEEN a.disputed_start AND a.disputed_end
        GROUP BY s.task_id
      )
      SELECT s.task_id,s.security_id,s.decision_date,o.cik,
        o.cik_count,o.bad_names,episode.full_window_episodes,
        aliases.other_active_security_ids,reviewed.known_discontinuity
      FROM selected_box s JOIN own o USING(task_id)
      JOIN episode USING(task_id) JOIN aliases USING(task_id)
      JOIN reviewed USING(task_id) ORDER BY s.task_id""").fetchall()
    names = ("task_id", "security_id", "decision_date", "cik", "cik_count",
             "bad_names", "full_window_episodes", "other_active_security_ids",
             "known_discontinuity")
    return [dict(zip(names, row)) for row in rows]


def classify(row: dict) -> str:
    if row["cik_count"] != 1 or row["full_window_episodes"] != 1:
        return "AMBIGUOUS_OWN_IDENTITY"
    if row["bad_names"] or row["known_discontinuity"]:
        return "KNOWN_IDENTITY_CONFLICT"
    if row["other_active_security_ids"]:
        return "CONTEMPORANEOUS_ISSUER_ALIAS"
    return "OBSERVATIONAL_NO_KNOWN_CONFLICT"


def audit(research_root: Path, selection_path: Path,
          expected_selection_sha256: str, output_path: Path) -> dict:
    if output_path.exists():
        raise FileExistsError("private alias receipt already exists")
    selection_raw = selection_path.read_bytes()
    if digest(selection_raw) != expected_selection_sha256:
        raise ValueError("frozen selection hash mismatch")
    selection = json.loads(selection_raw)
    if (selection.get("version") != VERSION
            or selection.get("selection_precedes_detector") is not True
            or len(selection.get("rows", [])) != 48):
        raise ValueError("expected frozen Stage B selection")
    source_path, source_hash = construction_source(research_root)
    windows = []
    with BoxHistory(research_root) as provider:
        if provider.semantic_hash != selection["ri_semantic_hash"]:
            raise ValueError("frozen RI semantics drift")
        for row in selection["rows"]:
            history = provider.history(row["security_id"], row["decision_date"], 126)
            windows.append({"task_id": row["task_id"],
                "security_id": row["security_id"],
                "decision_date": row["decision_date"],
                "window_start": str(history.date.iloc[0].date())})
    with duckdb.connect(str(source_path), read_only=True) as connection:
        rows = dated_evidence(connection, windows)
    if len(rows) != 48 or len({r["task_id"] for r in rows}) != 48:
        raise ValueError("issuer audit lost or duplicated frozen tasks")
    for row in rows:
        row["classification"] = classify(row)
    private = {"version": "box-issuer-alias-asof-t-v1",
               "selection_sha256": expected_selection_sha256,
               "construction_sha256": source_hash,
               "ri_semantic_hash": selection["ri_semantic_hash"],
               "official_identity_certified": False,
               "rows": rows}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw = packed(private)
    output_path.write_bytes(raw)
    return {"version": private["version"],
            "selection_sha256": expected_selection_sha256,
            "construction_sha256": source_hash,
            "private_receipt_sha256": digest(raw),
            "selected": len(rows),
            "classifications": dict(sorted(Counter(r["classification"] for r in rows).items())),
            "other_active_security_id_counts": dict(sorted(Counter(
                r["other_active_security_ids"] for r in rows).items())),
            "official_identity_certified": False,
            "future_outcomes_read": False,
            "human_labels_read": False}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--expected-selection-sha256", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(audit(args.research_root, args.selection,
                           args.expected_selection_sha256, args.output),
                     ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

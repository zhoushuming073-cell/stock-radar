"""Read-only T+1 execution-metadata preflight for frozen box diagnostics.

This does not read Open/Close values, infer fills, calculate outcomes, or make
the observational sample a formally executable LEAN dataset.
"""
from __future__ import annotations

import argparse
from collections import Counter
import json
from pathlib import Path

import pandas as pd

from radar.box_labeling.history import BoxHistory
from radar.box_labeling.stage_b import VERSION as SELECTION_VERSION, digest, packed


def read_frozen(path: Path, expected_sha256: str) -> dict:
    raw = path.read_bytes()
    if digest(raw) != expected_sha256:
        raise ValueError("private input hash mismatch")
    return json.loads(raw)


def next_session_metadata(connection, rows: list[dict]) -> list[dict]:
    """Only session and provenance columns; no OHLCV or future labels."""
    connection.register("box_preflight", pd.DataFrame(rows))
    values = connection.execute("""WITH next_day AS (
        SELECT b.task_id,min(s.date) AS next_session
        FROM box_preflight b LEFT JOIN sessions s
          ON s.date>CAST(b.decision_date AS DATE)
        GROUP BY b.task_id
      )
      SELECT b.task_id,n.next_session,count(p.date) AS total_price_rows,
        count(p.date) FILTER (WHERE p.source=b.source AND p.basis=b.basis)
          AS matching_price_rows,
        min(p.source) FILTER (WHERE p.source=b.source AND p.basis=b.basis) AS source,
        min(p.basis) FILTER (WHERE p.source=b.source AND p.basis=b.basis) AS basis,
        bool_and(p.shape_research_ready) FILTER (
          WHERE p.source=b.source AND p.basis=b.basis) AS all_ready,
        bool_or(p.identity_conflict OR p.class_or_name_boundary) FILTER (
          WHERE p.source=b.source AND p.basis=b.basis) AS identity_flag,
        bool_or(p.known_split OR p.invalid_split_action OR p.suspected_split) FILTER (
          WHERE p.source=b.source AND p.basis=b.basis) AS split_flag,
        min(p.membership_status) FILTER (
          WHERE p.source=b.source AND p.basis=b.basis) AS membership_status
      FROM box_preflight b JOIN next_day n USING(task_id)
      LEFT JOIN shape_price p ON p.security_id=b.security_id
        AND p.date=n.next_session
      GROUP BY b.task_id,n.next_session ORDER BY b.task_id""").fetchall()
    columns = ("task_id", "next_session", "total_price_rows", "matching_price_rows", "source", "basis",
               "all_ready", "identity_flag", "split_flag", "membership_status")
    return [dict(zip(columns, row)) for row in values]


def reasons(row: dict, expected: dict) -> tuple[str, ...]:
    issues = []
    if row["next_session"] is None:
        issues.append("no_next_session_in_frozen_core")
    if row["total_price_rows"] == 0:
        issues.append("no_next_security_bar")
    elif row["matching_price_rows"] == 0:
        issues.append("next_source_basis_unavailable")
    elif row["matching_price_rows"] != 1:
        issues.append("duplicate_matching_source_basis")
    else:
        if row["source"] != expected["source"]:
            issues.append("source_changed")
        if row["basis"] != expected["basis"]:
            issues.append("basis_changed")
        if row["all_ready"] is not True:
            issues.append("next_bar_not_research_ready")
        if row["identity_flag"]:
            issues.append("next_bar_identity_flag")
        if row["split_flag"]:
            issues.append("next_bar_split_flag")
        if row["membership_status"] not in {"confirmed_member", "probable_member"}:
            issues.append("next_membership_not_supported")
    return tuple(issues)


def audit(research_root: Path, selection_path: Path, selection_sha256: str,
          context_path: Path, context_sha256: str, alias_path: Path,
          alias_sha256: str, output_path: Path) -> dict:
    if output_path.exists():
        raise FileExistsError("private execution preflight already exists")
    selection = read_frozen(selection_path, selection_sha256)
    context = read_frozen(context_path, context_sha256)
    aliases = read_frozen(alias_path, alias_sha256)
    if (selection.get("version") != SELECTION_VERSION
            or context.get("version") != "box-lower-band-stage-c-diagnostic-v1"
            or aliases.get("version") != "box-issuer-alias-asof-t-v1"
            or context.get("selection_sha256") != selection_sha256
            or aliases.get("selection_sha256") != selection_sha256):
        raise ValueError("frozen research inputs do not share one selection")
    selected = {r["task_id"]: r for r in selection["rows"]}
    contextual = {r["task_id"]: r for r in context["rows"]}
    identified = {r["task_id"]: r for r in aliases["rows"]}
    if len(selected) != 48 or set(selected) != set(contextual) or set(selected) != set(identified):
        raise ValueError("missing or duplicated frozen task")
    for task_id, row in selected.items():
        if any(part["security_id"] != row["security_id"] or
               part["decision_date"] != row["decision_date"]
               for part in (contextual[task_id], identified[task_id])):
            raise ValueError("private identity/date mapping drift")
    eligible = [r for r in selection["rows"] if identified[r["task_id"]]["classification"]
                == "OBSERVATIONAL_NO_KNOWN_CONFLICT"]
    if not eligible:
        raise ValueError("no observationally conflict-free diagnostic rows")
    query = [{"task_id": r["task_id"], "security_id": r["security_id"],
              "decision_date": r["decision_date"], "source": r["source"],
              "basis": r["basis"]} for r in eligible]
    with BoxHistory(research_root) as provider:
        if provider.semantic_hash != selection["ri_semantic_hash"]:
            raise ValueError("RI v1 semantic hash drift")
        metadata = next_session_metadata(provider.api.core.connection, query)
    if len(metadata) != len(eligible):
        raise ValueError("execution metadata lost a diagnostic task")
    by_id = {r["task_id"]: r for r in eligible}
    for row in metadata:
        row["next_session"] = str(row["next_session"]) if row["next_session"] else None
        row["issues"] = reasons(row, by_id[row["task_id"]])
        row["quantile_state"] = contextual[row["task_id"]]["contexts"]["quantile-zone-v1"]["state"]
        row["pivot_state"] = contextual[row["task_id"]]["contexts"]["confirmed-pivot-zone-v1"]["state"]
    private = {"version": "box-execution-metadata-preflight-v1",
               "selection_sha256": selection_sha256,
               "context_sha256": context_sha256,
               "alias_sha256": alias_sha256,
               "ri_semantic_hash": selection["ri_semantic_hash"],
               "future_prices_read": False, "future_outcomes_read": False,
               "formal_lean_ready": False, "rows": metadata}
    output_path.parent.mkdir(parents=True, exist_ok=True)
    raw = packed(private)
    output_path.write_bytes(raw)
    return {"version": private["version"], "selection_sha256": selection_sha256,
            "private_receipt_sha256": digest(raw), "observational_rows_checked": len(metadata),
            "metadata_complete_rows": sum(not r["issues"] for r in metadata),
            "issues": dict(sorted(Counter(reason for r in metadata
                                          for reason in r["issues"]).items())),
            "alternative_source_or_basis_rows": sum(
                r["total_price_rows"] > r["matching_price_rows"] for r in metadata),
            "next_basis": dict(sorted(Counter(str(r["basis"]) for r in metadata).items())),
            "near_lower_quantile_rows": sum(r["quantile_state"] == "NEAR_LOWER_STABILIZING"
                                            for r in metadata),
            "near_lower_pivot_rows": sum(r["pivot_state"] == "NEAR_LOWER_STABILIZING"
                                         for r in metadata),
            "formal_lean_ready": False,
            "future_prices_read": False, "future_outcomes_read": False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--research-root", type=Path, required=True)
    p.add_argument("--selection", type=Path, required=True)
    p.add_argument("--selection-sha256", required=True)
    p.add_argument("--context", type=Path, required=True)
    p.add_argument("--context-sha256", required=True)
    p.add_argument("--aliases", type=Path, required=True)
    p.add_argument("--aliases-sha256", required=True)
    p.add_argument("--output", type=Path, required=True)
    a = p.parse_args()
    print(json.dumps(audit(a.research_root, a.selection, a.selection_sha256,
                           a.context, a.context_sha256, a.aliases,
                           a.aliases_sha256, a.output), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

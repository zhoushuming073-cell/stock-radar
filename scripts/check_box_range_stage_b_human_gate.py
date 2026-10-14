"""Read-only Stage B human-label progress gate; never computes detector quality."""
from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sqlite3

from radar.box_labeling.ontology_v11 import LABEL_VERSION, validate
from radar.box_labeling.stage_b import VERSION as SELECTION_VERSION, digest
from radar.box_labeling.store import DATASET_VERSION, GateError


def check(selection_path: Path, task_root: Path, detector_audit_path: Path,
          *, user_id: int | None = None, expected_tasks: int = 48) -> dict:
    selection_raw = selection_path.read_bytes()
    selection = json.loads(selection_raw)
    manifest_raw = (task_root / "manifest.json").read_bytes()
    manifest = json.loads(manifest_raw)
    receipt = json.loads((task_root / "receipt.json").read_bytes())
    detector_audit = json.loads(detector_audit_path.read_bytes())
    selection_hash = digest(selection_raw)
    manifest_hash = digest(manifest_raw)
    if (selection.get("version") != SELECTION_VERSION
            or not selection.get("selection_precedes_detector")
            or len(selection["rows"]) != expected_tasks
            or len(manifest) != expected_tasks
            or receipt.get("version") != DATASET_VERSION
            or receipt.get("task_count") != expected_tasks
            or receipt.get("selection_sha256") != selection_hash
            or receipt.get("manifest_hash") != manifest_hash
            or detector_audit.get("selection_sha256") != selection_hash
            or len(detector_audit.get("blind", [])) != expected_tasks):
        raise GateError("Stage B frozen selection, task receipt or detector audit drift")
    selected_ids = {row["task_id"] for row in selection["rows"]}
    tasks = {row["task_id"]: row for row in manifest}
    audited_ids = {row["task_id"] for row in detector_audit["blind"]}
    if (len(selected_ids) != expected_tasks or len(tasks) != expected_tasks
            or len(audited_ids) != expected_tasks
            or selected_ids != set(tasks) or selected_ids != audited_ids):
        raise GateError("Stage B task mapping drift")
    for row in selection["rows"]:
        task = tasks[row["task_id"]]
        audited = next(item for item in detector_audit["blind"]
                       if item["task_id"] == row["task_id"])
        if (task["security_id"] != row["security_id"]
                or task["decision_date"] != row["decision_date"]
                or audited["security_id"] != row["security_id"]
                or audited["decision_date"] != row["decision_date"]):
            raise GateError("Stage B private task identity drift")

    db = task_root / "annotations-v1.1-human.sqlite3"
    if not db.is_file():
        return {"status": "AWAITING_HUMAN", "labeled_tasks": 0,
                "total_tasks": expected_tasks, "annotation_revisions": 0,
                "selection_sha256": selection_hash, "manifest_sha256": manifest_hash}
    with sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True) as connection:
        rows = connection.execute("""SELECT id,task,user,revision,body FROM annotation
            ORDER BY user,task,revision""").fetchall()
    users = {row[2] for row in rows}
    if user_id is None and len(users) > 1:
        raise GateError("multiple human reviewers; specify --user-id")
    selected_user = user_id if user_id is not None else next(iter(users), None)
    revisions: dict[tuple[int, str], int] = defaultdict(int)
    latest: dict[str, dict] = {}
    for annotation_id, task_id, owner, revision, body in rows:
        if task_id not in tasks or revision != revisions[(owner, task_id)] + 1:
            raise GateError("unknown task or noncontiguous human revision")
        record = json.loads(body)
        task = tasks[task_id]
        if (record.get("annotation_id") != annotation_id
                or record.get("task_id") != task_id
                or record.get("user_id") != owner
                or record.get("revision") != revision
                or record.get("label_version") != LABEL_VERSION
                or record.get("dataset_version") != DATASET_VERSION
                or record.get("security_id") != task["security_id"]
                or record.get("decision_date") != task["decision_date"]
                or record.get("tensor_hashes") != {
                    k: v["tensor_hash"] for k, v in task["scales"].items()}
                or record.get("render_hashes") != {
                    k: v["chart_hash"] for k, v in task["scales"].items()}):
            raise GateError("human annotation provenance drift")
        validate({**record["label"], "expected_revision": revision - 1,
                  "label_version": LABEL_VERSION})
        revisions[(owner, task_id)] = revision
        if owner == selected_user:
            latest[task_id] = record
    labeled = len(latest)
    return {"status": ("LABEL_SET_COMPLETE_QUALITY_PENDING" if labeled == expected_tasks
                       else "AWAITING_HUMAN"),
            "labeled_tasks": labeled, "total_tasks": expected_tasks,
            "annotation_revisions": sum(n for (owner, _), n in revisions.items()
                                        if owner == selected_user),
            "selection_sha256": selection_hash, "manifest_sha256": manifest_hash,
            "detector_quality_computed": False, "future_outcomes_read": False}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--task-root", type=Path, required=True)
    parser.add_argument("--detector-audit", type=Path, required=True)
    parser.add_argument("--user-id", type=int)
    args = parser.parse_args()
    print(json.dumps(check(args.selection, args.task_root, args.detector_audit,
                           user_id=args.user_id), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

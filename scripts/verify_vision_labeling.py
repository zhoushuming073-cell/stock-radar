from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path

import pandas as pd


FORBIDDEN_KEYS = {
    "ticker", "symbol", "security_id", "decision_date", "date",
    "future", "future_return", "profit", "label", "outcome", "strategy2_score",
}


def file_hash(path: Path) -> str:
    h = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def verify(bundle: Path) -> dict:
    manifest = pd.read_parquet(bundle / "sample-manifest.parquet")
    pairs = pd.read_parquet(bundle / "pair-manifest.parquet")
    receipt = json.loads((bundle / "bundle-receipt.json").read_text(encoding="utf-8"))
    single_tasks = json.loads((bundle / "label-studio-single-tasks.json").read_text(encoding="utf-8"))
    pair_tasks = json.loads((bundle / "label-studio-pair-tasks.json").read_text(encoding="utf-8"))

    if receipt.get("future_outcomes_read") is not False or receipt.get("strategy2_scores_read") is not False:
        raise ValueError("bundle receipt indicates forbidden research inputs")
    if receipt.get("unknown_membership_included") is not False:
        raise ValueError("pilot unexpectedly includes unknown membership")

    manifest_ids = set(manifest["task_id"].astype(str))
    pair_ids = set(pairs["pair_id"].astype(str))
    if {str(x["data"].get("task_id")) for x in single_tasks} != manifest_ids:
        raise ValueError("single task/manifest mismatch")
    if {str(x["data"].get("pair_id")) for x in pair_tasks} != pair_ids:
        raise ValueError("pair task/manifest mismatch")

    for task in [*single_tasks, *pair_tasks]:
        data = task.get("data", {})
        leaked = FORBIDDEN_KEYS.intersection({str(k).lower() for k in data})
        if leaked:
            raise ValueError("Label Studio-visible identity/outcome key: " + ",".join(sorted(leaked)))
        for value in data.values():
            text = str(value).lower()
            if "sec-" in text or "strategy2" in text:
                raise ValueError("Label Studio-visible value contains internal identity/strategy token")

    bad_hashes = []
    for row in manifest.itertuples(index=False):
        image = bundle / str(row.image_path)
        if not image.is_file() or file_hash(image) != str(row.image_sha256):
            bad_hashes.append(str(row.task_id))
    if bad_hashes:
        raise ValueError(f"image hash mismatch: {len(bad_hashes)} tasks")

    if manifest["split_assignment"].isin(["test", "fresh_oos"]).any():
        raise ValueError("P0/P1 pilot touched Historical Test/Fresh")
    if not manifest["membership_status"].isin(["confirmed_member", "probable_member"]).all():
        raise ValueError("unsupported membership entered pilot")

    return {
        "status": "PASS",
        "single_tasks": len(single_tasks),
        "pairs": len(pair_tasks),
        "unique_images": int(manifest["blind_id"].nunique()),
        "repeats": int((manifest["task_kind"] == "single_repeat").sum()),
        "splits": sorted(set(manifest["split_assignment"].astype(str))),
        "image_hashes_verified": len(manifest),
        "visible_identity_or_outcome_fields": 0,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Verify a generated blind labeling bundle.")
    parser.add_argument("--bundle", type=Path, default=Path("data/vision-research/pilot-v1"))
    args = parser.parse_args()
    print(json.dumps(verify(args.bundle), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

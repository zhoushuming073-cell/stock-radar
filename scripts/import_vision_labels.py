from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from radar.vision.labeling import import_label_studio_export, repeat_consistency


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate and normalize a Label Studio export.")
    parser.add_argument("export", type=Path)
    parser.add_argument("--bundle", type=Path, default=Path("data/vision-research/pilot-v1"))
    parser.add_argument("--output", type=Path, default=Path("data/vision-research/pilot-v1/human-labels.parquet"))
    parser.add_argument("--label-version", default="human-vision-v1")
    args = parser.parse_args()

    manifest_path = args.bundle / "sample-manifest.parquet"
    pair_path = args.bundle / "pair-manifest.parquet"
    labels = import_label_studio_export(
        args.export,
        manifest_path,
        pair_path,
        label_version=args.label_version,
        output_path=args.output,
    )
    manifest = pd.read_parquet(manifest_path)
    summary = {
        "labels": len(labels),
        "single": int((labels.task_kind == "single").sum()) if not labels.empty else 0,
        "pair": int((labels.task_kind == "pair").sum()) if not labels.empty else 0,
        "repeat_consistency": repeat_consistency(labels, manifest),
        "future_outcomes_joined": False,
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

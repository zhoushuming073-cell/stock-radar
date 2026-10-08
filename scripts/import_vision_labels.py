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
    parser.add_argument("--output", type=Path)
    parser.add_argument('--kind',choices=['single','pair'],required=True)
    parser.add_argument('--smoke',action='store_true',help='NOT HUMAN GROUND TRUTH; isolated label namespace')
    parser.add_argument("--label-version", default="human-vision-v1")
    args = parser.parse_args()
    if args.smoke:
        args.label_version='smoke-vision-v1'
        output=args.bundle.parent/'smoke'/f'smoke-{args.kind}-labels.parquet'
        if args.output is not None and args.output.resolve()!=output.resolve():
            parser.error('Smoke labels must use the isolated smoke output')
    else:
        output=args.output or args.bundle/f'human-{args.kind}-labels.parquet'

    manifest_path = args.bundle / "sample-manifest.parquet"
    pair_path = args.bundle / "pair-manifest.parquet"
    labels = import_label_studio_export(
        args.export,
        manifest_path,
        pair_path,
        label_version=args.label_version,
        output_path=None,
    )
    if not labels.empty and set(labels.task_kind)!={args.kind}:
        parser.error('Single and Pair exports must be imported separately')
    output.parent.mkdir(parents=True,exist_ok=True)
    if output.exists():
        old=pd.read_parquet(output)
        if not old.empty and set(old.label_version)!={args.label_version}:
            parser.error('Refusing to mix label versions')
        labels=pd.concat([old,labels],ignore_index=True).drop_duplicates('task_id',keep='last')
    labels.to_parquet(output,index=False)
    manifest = pd.read_parquet(manifest_path)
    summary = {
        "labels": len(labels),
        "single": int((labels.task_kind == "single").sum()) if not labels.empty else 0,
        "pair": int((labels.task_kind == "pair").sum()) if not labels.empty else 0,
        "repeat_consistency": repeat_consistency(labels, manifest),
        "future_outcomes_joined": False,
        'label_version':args.label_version,
        'purpose':'SMOKE / NOT HUMAN GROUND TRUTH' if args.smoke else 'USER HUMAN GROUND TRUTH',
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Create a private immutable Stage B blind selection and chart task batch."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from radar.box_labeling.stage_b import freeze_blind_pool, materialize_blind_tasks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("freeze", "materialize"))
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--selection", type=Path, required=True)
    parser.add_argument("--prior-manifest", type=Path)
    parser.add_argument("--tasks-root", type=Path)
    parser.add_argument("--selection-sha256")
    parser.add_argument("--per-year", type=int, default=12)
    args = parser.parse_args()
    if args.action == "freeze":
        if not args.prior_manifest:
            parser.error("freeze requires --prior-manifest")
        result = freeze_blind_pool(args.research_root, args.selection,
                                   args.prior_manifest, per_year=args.per_year)
    else:
        if not args.tasks_root or not args.selection_sha256:
            parser.error("materialize requires --tasks-root and --selection-sha256")
        result = materialize_blind_tasks(args.research_root, args.selection,
                                         args.tasks_root, args.selection_sha256)
    print(json.dumps(result, sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

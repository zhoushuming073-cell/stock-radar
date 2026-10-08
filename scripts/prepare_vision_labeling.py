from __future__ import annotations

import argparse
import json
from pathlib import Path

from radar.vision.labeling import build_label_studio_bundle


def main() -> int:
    parser = argparse.ArgumentParser(description="Build blind P0/P1 Label Studio tasks.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--config", type=Path, default=Path("config/vision_research_v1.yaml"))
    args = parser.parse_args()
    receipt = build_label_studio_bundle(args.root, args.root / args.config)
    print(json.dumps(receipt, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

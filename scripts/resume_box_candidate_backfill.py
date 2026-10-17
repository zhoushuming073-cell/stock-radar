"""Preflight sealed candidate receipts before resuming the existing writer.

The scanner itself stays frozen while code-bound private chunks are produced.
This wrapper rejects unexpected/partial artifacts through its verify-only path
before asking that same scanner to create any missing chunks.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from scripts.scan_box_near_lower_stage_d import execute


def resume(research_root: Path, split: str, start: str, end: str,
           output_dir: Path, detector_config: Path, context_config: Path,
           chunk_size: int = 256, max_new_chunks: int | None = None) -> dict:
    preflight = execute(research_root, split, start, end, output_dir,
                        detector_config, context_config, chunk_size,
                        verify_only=True)
    if preflight["complete"]:
        return {"preflight": preflight, "run": None,
                "already_complete": True}
    run = execute(research_root, split, start, end, output_dir,
                  detector_config, context_config, chunk_size,
                  max_new_chunks=max_new_chunks)
    return {"preflight": preflight, "run": run,
            "already_complete": False}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--research-root", type=Path, required=True)
    parser.add_argument("--split", choices=("train", "validation"), required=True)
    parser.add_argument("--start", required=True)
    parser.add_argument("--end", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--detector-config", type=Path,
                        default=Path("config/box_range_detector_stage_a_v1.yaml"))
    parser.add_argument("--context-config", type=Path,
                        default=Path("config/box_lower_band_context_v1.yaml"))
    parser.add_argument("--chunk-size", type=int, default=256)
    parser.add_argument("--max-new-chunks", type=int)
    args = parser.parse_args()
    print(json.dumps(resume(args.research_root, args.split, args.start,
                            args.end, args.output_dir, args.detector_config,
                            args.context_config, args.chunk_size,
                            args.max_new_chunks), sort_keys=True, indent=2))


if __name__ == "__main__":
    main()

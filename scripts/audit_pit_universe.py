"""Read-only comparison and price-coverage audit for a pinned PIT build."""
import argparse
import json
from pathlib import Path

from radar.lab.universe import LocalSecurityMaster
from radar.pit.audit import membership_report, price_coverage_report
from radar.pit.validation import validation_report


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--database", type=Path, default=Path("data/phase2-research.duckdb"))
    p.add_argument("--output", type=Path)
    p.add_argument("--cache", type=Path, default=Path("data/pit/raw"))
    args = p.parse_args()
    master = LocalSecurityMaster(args.build / "security-master.csv", args.build / "security-master-manifest.json")
    output = args.output or Path("data/pit/reports") / master.manifest["source_version"]
    print(json.dumps(membership_report(master, args.database, output)), flush=True)
    print(json.dumps(price_coverage_report(master, args.database, output)), flush=True)
    lock = args.build / "source-lock.json"
    if lock.exists():
        print(json.dumps(validation_report(master, args.cache, json.loads(lock.read_text(encoding="utf-8")), output, args.database)), flush=True)


if __name__ == "__main__":
    main()

"""Build PIT features separately, then bind them to an immutable master build."""
import argparse
import json
from pathlib import Path

from radar.lab.universe import LocalSecurityMaster
from radar.pit.features import build_features


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--source", type=Path, default=Path("data/phase2-research.duckdb"))
    p.add_argument("--config", type=Path, default=Path("config/research.yaml"))
    p.add_argument("--external-prices", type=Path)
    args = p.parse_args()
    master = LocalSecurityMaster(args.build / "security-master.csv", args.build / "security-master-manifest.json")
    destination = args.build / "pit-research.duckdb"
    manifest = build_features(args.source, master, args.config, destination,
                             lambda value: print(json.dumps(value), flush=True),
                             external_prices=args.external_prices)
    (args.build / "security-master-feature-store.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest), flush=True)


if __name__ == "__main__":
    main()

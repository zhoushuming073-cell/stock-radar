"""Download explicitly, pin commits, reconstruct locally, optionally install.

No network occurs without --download/--update. No existing market/research
database is opened for writing. Source data and generated artifacts are ignored.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
from pathlib import Path
import shutil
import subprocess

from radar.pit.builder import apply_verified_evidence, load_identity_evidence, reconstruct, write_build
from radar.pit.sources import REPOSITORIES, download, git, history, pin

ROOT = Path(__file__).resolve().parents[1]


def install_build(build: Path, root: Path) -> None:
    """Preflight the complete contract before copying into the data directory."""
    names = ["security-master.csv", "security-master-manifest.json", "security-master-feature-store.json"]
    if not all((build / name).is_file() for name in names):
        raise ValueError("build PIT features before installation; immutable master build retained")
    targets = [root / "data" / name for name in names]
    if any(path.exists() for path in targets):
        raise ValueError("installed master already exists; immutable build retained; installation refused")
    from radar.lab.universe import LocalSecurityMaster
    LocalSecurityMaster(build / names[0], build / names[1])
    (root / "data").mkdir(parents=True, exist_ok=True)
    for target in targets:
        shutil.copy2(build / target.name, target)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start", type=date.fromisoformat, default=date(2021, 9, 1))
    parser.add_argument("--end", type=date.fromisoformat, required=True)
    parser.add_argument("--cache", type=Path, default=ROOT / "data/pit/raw")
    parser.add_argument("--output", type=Path, default=ROOT / "data/pit/normalized")
    parser.add_argument("--download", action="store_true")
    parser.add_argument("--update", action="store_true")
    parser.add_argument("--lock", type=Path, help="Replay exact source commits from a previous lock")
    parser.add_argument("--identity-evidence", type=Path)
    parser.add_argument("--max-stale-days", type=int, default=4)
    parser.add_argument("--install", action="store_true", help="Install only if no existing master is present")
    args = parser.parse_args()
    aliases = {"symbols": "us-stock-symbols", "delisted": "delisted-equity-data",
               "reference": "ticker-reference-data"}
    pins = json.loads(args.lock.read_text(encoding="utf-8")) if args.lock else {}
    repositories = {}
    for name in REPOSITORIES:
        existing = args.cache / (aliases[name] + ".git")
        repo = existing if existing.exists() else args.cache / (name + ".git")
        if args.download or args.update:
            if existing.exists():
                if args.update:
                    git(existing, "fetch", "origin", "+refs/heads/*:refs/heads/*")
            else:
                repo = download(args.cache, name, update=args.update)
        if not repo.exists():
            if name == "symbols":
                parser.error("missing symbols cache; use --download")
            continue
        sha = pins[name]["commit"] if name in pins else pin(repo, args.end)
        git(repo, "cat-file", "-e", sha + "^{commit}")
        repositories[name] = repo
        paths = git(repo, "ls-tree", "-r", "--name-only", sha).decode().splitlines()
        licenses = [p for p in paths if Path(p).name.upper().startswith(("LICENSE", "COPYING"))]
        pins[name] = {"repository": REPOSITORIES[name], "commit": sha,
                      "license_files": licenses, "redistribution": "unverified; raw stays local"}
    evidence = load_identity_evidence(args.identity_evidence)
    def snapshots():
        for i, snapshot in enumerate(history(repositories["symbols"], pins["symbols"]["commit"],
                                             args.start, args.end)):
            if i % 100 == 0:
                print(json.dumps({"snapshot": i, "date": str(snapshot.day)}), flush=True)
            yield snapshot
    frame, report = reconstruct(snapshots(), args.start, args.end,
                                max_stale_days=args.max_stale_days, identity_evidence=evidence)
    frame, report["identity_corrections"] = apply_verified_evidence(
        frame, evidence, max_stale_days=args.max_stale_days)
    report.update({"intervals": len(frame), "security_ids": int(frame.security_id.nunique()),
                   "unresolved_intervals": int(frame.resolution_status.ne("verified").sum())})
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True,
                            text=True, check=True).stdout.strip()
    manifest = write_build(args.output, frame, report, start=args.start, end=args.end,
                           source_pins=pins, stock_radar_commit=commit,
                           max_stale_days=args.max_stale_days, identity_evidence=evidence)
    build = args.output / manifest["source_version"]
    (build / "source-lock.json").write_text(json.dumps(pins, indent=2), encoding="utf-8")
    if args.install:
        try:
            install_build(build, ROOT)
        except ValueError as exc:
            parser.error(str(exc))
    print(json.dumps({"build": str(build), "version": manifest["source_version"],
                      "intervals": report["intervals"], "securities": report["security_ids"],
                      "source_gaps": report["source_gaps"], "anomalies": len(report["anomalies"]),
                      "unresolved_intervals": report["unresolved_intervals"],
                      "formal_pit_ready": False}), flush=True)


if __name__ == "__main__":
    main()

"""Offline enrichment; one existing contract, immutable parent/child versions."""
import argparse
from datetime import date
import hashlib
import json
from pathlib import Path
import subprocess

from radar.lab.universe import LocalSecurityMaster
from radar.pit.builder import digest, write_build
from radar.pit.trust import enrich, load_catalog, episode_candidates

def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--build", type=Path, required=True)
    p.add_argument("--catalog", type=Path, default=Path("config/pit_trust_evidence.json"))
    p.add_argument("--raw", type=Path, default=Path("data/pit/raw/official-evidence"))
    p.add_argument("--output", type=Path, default=Path("data/pit/normalized"))
    a = p.parse_args()
    master = LocalSecurityMaster(a.build / "security-master.csv", a.build / "security-master-manifest.json")
    catalog = load_catalog(a.catalog, a.raw)
    frame, evidence = enrich(master.frame, catalog)
    report = json.loads((a.build / "snapshot-audit.json").read_text(encoding="utf-8"))
    report.update({"intervals": len(frame), "security_ids": int(frame.security_id.nunique()),
                   "unresolved_intervals": int(frame.resolution_status.ne("verified").sum()),
                   "unknown_type_intervals": int(frame.security_type.eq("unknown").sum()),
                   "trust_enrichment": evidence})
    pins = json.loads((a.build / "source-lock.json").read_text(encoding="utf-8"))
    pins["trust_evidence"] = {"catalog_sha256": digest(catalog), "parent_master_sha256": master.manifest["output_sha256"],
        "resolver_code_sha256": hashlib.sha256(Path(__import__('radar.pit.trust', fromlist=['x']).__file__).read_bytes()).hexdigest(),
        "driver_code_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    manifest = write_build(a.output, frame, report, start=master.coverage_start.date(), end=master.coverage_end.date(),
        source_pins=pins, stock_radar_commit=subprocess.check_output(["git", "rev-parse", "HEAD"]).decode().strip(),
        max_stale_days=master.manifest["max_stale_days"], identity_evidence=catalog["mappings"])
    build = a.output / manifest["source_version"]
    (build / "source-lock.json").write_text(json.dumps(pins, indent=2), encoding="utf-8")
    (build / "trust-evidence.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    (build / "episode-candidates.json").write_text(json.dumps(episode_candidates(frame), indent=2), encoding="utf-8")
    LocalSecurityMaster(build / "security-master.csv", build / "security-master-manifest.json")
    print(json.dumps({"build": str(build), "version": manifest["source_version"], "decisions": len(evidence["decisions"])}))

if __name__ == "__main__":
    main()

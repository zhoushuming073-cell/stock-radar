"""Read-only, private dependency worksheet for the existing frozen Q1 study."""
from pathlib import Path
import argparse
import json

from radar.pit.quant_execution_closure import artifact_hash, public_summary, worksheet
from radar.research.infrastructure import ResearchInfrastructure
from radar.research.quant_lean import verify_freeze
from radar.research.candidates import code_hash


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--root", type=Path, default=Path.cwd())
    a = p.parse_args();root = a.root.resolve()
    study = root / "data/research/quant-research-v1"
    receipt_path = study / "freeze.json"
    if artifact_hash(receipt_path) != "7a175ee6fe9b5815207e5d1a964213cf005a11b4cbd4b16e27856f3f46a96efd":
        raise ValueError("unexpected existing study receipt")
    if code_hash() != "4e5d9f15e7002977a74d67d1637c24a2da28c0cf11414696dece2090485962a8":
        raise ValueError("frozen selector drift")
    receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
    verify_freeze(root, receipt)
    records = []
    candidate_hashes = {}
    with ResearchInfrastructure(root) as api:
        for split in ("train", "validation"):
            path = study / split / "candidates.jsonl"
            candidate_hashes[split] = artifact_hash(path)
            rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
            gate = json.loads((study / split / "q1-execution-gate.json").read_text(encoding="utf-8"))
            items = worksheet(api.core.connection, rows, receipt["research_config"]["intervals"][split], gate["failures"])
            records.extend({"split": split, **item} for item in items)
    payload = {"version": "q1-execution-dependencies-v1", "freeze_sha256": artifact_hash(receipt_path),
               "candidate_file_sha256": candidate_hashes, "dependencies": records}
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False, indent=2).encode("utf-8")
    import hashlib
    sha = hashlib.sha256(encoded).hexdigest()
    out = root / "data/research/q1-execution-closure-v1/worksheets" / (sha + ".json")
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists() and out.read_bytes() != encoded:
        raise ValueError("immutable worksheet collision")
    if not out.exists():out.write_bytes(encoded)
    verify_freeze(root, receipt)
    print(json.dumps({**public_summary(records), "private_worksheet": str(out), "worksheet_sha256": sha}, indent=2))


if __name__ == "__main__":main()

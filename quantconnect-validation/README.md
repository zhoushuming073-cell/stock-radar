# Stock Radar QuantConnect Free Validation

Independent validation only. Production Stock Radar does not import this directory.

Status: **PARTIAL**. Both actual Cloud smoke data checks were observed PASS on 2026-10-08; full downloaded receipts remain pending. Layers1–3 are **NOT_RUN**, and their import gate remains locked. See the [actual Cloud report](../reports/qc-cloud-smoke-validation-2026-10-08.md).

- `projects/`: two self-contained, single-file Cloud smoke projects.
- `cloud/`: QC-only data transport and derived-output protocol.
- `snapshots/`: AST-generated local formulas, feature functions, plugin and execution source. Import relocation only; source/generated hashes live in the freeze.
- `frozen/inputs.json`: hash-bound local Core, dated identity references, P0 unknown competitors and causal C signals. Own local data, never QC market exports.
- `campaign.json`: predetermined 235 sessions per data layer; full continuous execution window.
- `quota-audit.json`: all470 date projects audited, including late dates.
- `schemas/`, `evidence.py`: structured evidence and deterministic validation.
- `local.py`: prepare/stage/verify/import/compare and execution-detail merge.
- `work/`, `results/`: ignored staging and private actual Cloud downloads.

Run from the repository root with `.venv/Scripts/python.exe -B quantconnect-validation/local.py`.
After two actual Cloud smoke PASS receipts, stage a run from the campaign. Preview packs deliberately refuse execution until real prerequisites exist. No Object Store writes, paid API/CLI, current-list fallback, or raw QC bar exports.

The source snapshots are generated artifacts, not a second strategy owner. If source/config/transport changes, regenerate a new frozen campaign and repeat the applicable Cloud smoke. Never tune parameters to fit a Cloud result.

Full mechanical instructions: [QUANTCONNECT_FREE_VALIDATION.md](../docs/QUANTCONNECT_FREE_VALIDATION.md).
Readiness/limitations: [acceptance report](../reports/qc-cloud-validation-readiness-2026-10-07.md).

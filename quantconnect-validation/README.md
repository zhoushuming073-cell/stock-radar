# Stock Radar QuantConnect Free Validation

Independent validation only. Production Stock Radar does not import this directory.

Status: **PARTIAL / HOLD**. Both actual Cloud smoke full Logs/Results downloads were imported and parser-verified PASS on 2026-10-08. The first Layer1 pilot engine completed but its comparison receipt remains unverified; further batches/reference exports are on hold under the documented platform export-scope constraint. Layer2–3 remain **NOT_RUN**, and formal PIT remains **BLOCKED**. See the [actual Cloud report](../reports/acceptance/qc-cloud-smoke-validation-2026-10-08.md).

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
Both actual Cloud smoke PASS receipts are now imported. Do not continue the staged reference-export campaign while the documented platform export-scope hold remains in force. Preview packs continue to refuse execution when real prerequisites are absent. No Object Store writes, paid API/CLI, current-list fallback, or raw QC bar exports.

The source snapshots are generated artifacts, not a second strategy owner. If source/config/transport changes, regenerate a new frozen campaign and repeat the applicable Cloud smoke. Never tune parameters to fit a Cloud result.

Full mechanical instructions: [QUANTCONNECT_FREE_VALIDATION.md](../docs/QUANTCONNECT_FREE_VALIDATION.md).
Readiness/limitations: [acceptance report](../reports/acceptance/qc-cloud-validation-readiness-2026-10-07.md).

# Box Structure Labeling v1 — local operator guide

This workflow builds historical, causal box/range review tasks from frozen Research Infrastructure v1. Charts are for **human** judgment. Model inputs are numeric OHLCV only. The candidate prefilter is a high-recall retrieval aid, not a label or a profitability result.

## Open the current local page

Open `http://localhost:4174/lab.html#lab` and use the **Box Labeling** sidebar link. The destination is the existing authenticated local Label Studio extension at `http://localhost:8124/box-label/v1/human/`. Use the existing Label Studio login if prompted. Both services bind to loopback. 4174 is the Stock Radar navigation/site service; 8124 hosts the authenticated annotation route. No public/Sites deployment is involved.

The page displays historical Daily, Weekly and Monthly candlesticks ending at the same T close. It hides security identity, calendar date, candidate score, sampling stratum and any future outcome. For each chart select **Structure** (BOX / NOT_BOX / UNCERTAIN), **Current position** (LOWER / MIDDLE / UPPER / BREAKDOWN / UNCERTAIN), **Confidence**, and optional reasons/note. Save advances one task; Skip records an event without a label. Previous/Next navigate. Enter saves, S skips, U reverts unsaved form edits when focus is outside a form control. A saved task can be reopened and modified; the original remains as immutable revision 1.

The `human` route is for the user's genuine judgment. Automated checks use `/box-label/v1/smoke/`, backed by a separate `annotations-smoke.sqlite3`. Never copy smoke labels into human Ground Truth.

## Prepare a new local task set

From the repository root, with `PYTHONPATH=src` and the project's Python environment:

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
python scripts/prepare_box_labeling.py --research-root 'C:\path\to\stock-radar' --output data/box-label-v1-2m-1y-4y --config config/box_labeling_v1.yaml
python scripts/verify_box_labeling.py data/box-label-v1-2m-1y-4y
```

The output path must be new. A manifest or annotation database is never overwritten. The builder reads frozen RI v1 in place, with no database mutation or network calls. `data/` remains Git-ignored. The current 2026-10-11 batch is already prepared on this machine; do **not** rerun the builder into the same folder.

The 126-session plugin sees only past OHLCV. It returns a score and diagnostics stored privately. Sampling uses deterministic `seed=20261011` and 21 positive, 6 near-miss, 3 unconditional-control tasks (target 30). Security IDs are unique across the first batch. Train/Validation dates only. A different target or policy requires a new versioned output directory and audit.

Each task stores raw dated OHLCV per scale, normalized `float32` `[time,5]` arrays, SVGs, hashes and private identity/split/provenance metadata. The human and model windows are **Daily 42 trading sessions (about two months), Weekly 52 bars (one year), Monthly 48 bars (four years)**. The numeric normalization is `log(OHLC/T_close)` and `log1p(volume)/log1p(median volume in that past-only scale)`. The final partial week/month ends on T. Historical data starts in September 2021; earlier tasks cannot have four complete years. The page shows actual coverage, e.g. `12/48 bars`, and the tensor mask records incomplete scales without inventing older bars. The default `BoxHistory` requests up to 1,100 safe past sessions after RI v1 verifies the 126-session decision window. Its source/basis/safety checks reject unsafe or mixed histories.

## Start the local services

The existing project's Label Studio environment/login is reused. From this repository root:

```powershell
./scripts/start_box_labeling.ps1
```

It starts only the loopback annotation service at port 8124 and does not replace the older v3 labeling route or labels. The startup sets `LATEST_VERSION_CHECK=false` and empty Sentry endpoints so Label Studio does not perform its optional PyPI/version or error-telemetry calls. If 4174 is stopped, start the existing local site via `python scripts/serve-local-site.py`. The optional 8765 Stock Radar API is unrelated to this labeling route. When running from a development worktree, `start_box_labeling.ps1` finds the sibling `stock-radar` frozen data/login installation. After merging, it can run in the main checkout. Pass `-ResearchRoot` and `-CodeRoot` if the checkout layout differs.

## Numeric export and later training boundary

After **real** labels exist, export with a local authenticated user ID (the existing Label Studio user ID; inspect the local Django admin if uncertain):

```powershell
$env:PYTHONPATH=(Join-Path (Get-Location) 'src')
python -c "from radar.box_labeling.store import BoxStore; print(BoxStore('data/box-label-v1-2m-1y-4y','human').export_numeric(1,'data/box-label-v1-2m-1y-4y/exports/human.json'))"
```

The export contains only labeled examples and references verified local numeric `.npy` tensors. It has no chart pixels, candidate score, future return or outcome. `radar.box_labeling.trainer.load_export(path)` verifies tensor hashes and split groups without opening the historical database. `trainer.model_type()` supplies a small three-encoder 1D CNN with separate shape and position heads. `fit_numeric_export()` is a later authorized entry point with explicit seed, epochs, optional per-class weights, fixed Train/Validation groups, per-class metrics, calibration diagnostics and a checkpoint carrying code/config/export hashes. `synthetic_smoke()` checks a single optimizer step using generated fixtures only. **Do not train on actual human labels until a separate work order authorizes it.**

The `multi-scale-1d-cnn-v2-length-masked` scaffold uses the verified observed length of each scale. A partial 12/48-month sequence contributes its 12 real bars; padded slots contribute nothing to convolutional pooling. The existing `available` flag still means *full-length coverage* for reporting. Numeric tensor files and human annotation records are unchanged. Existing synthetic v1 checkpoints must not be loaded as v2 weights.

## Privacy and limits

The 30 tasks are a development batch, not market-wide performance evidence. The prefilter changes the sampling distribution; the control channel makes some misses observable but does not make this a representative market sample. Frozen RI v1 still has its documented historical membership and disappeared-security coverage limits. No future Y or portfolio backtest was read or produced by this workflow. All market charts, private mappings, saved labels, model exports, database files and login credentials stay under ignored local `data/`.

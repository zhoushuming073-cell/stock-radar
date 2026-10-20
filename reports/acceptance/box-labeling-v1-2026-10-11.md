# Box Structure Numeric Labeling v1 — local acceptance, 2026-10-11

## Decision

**Local engineering READY for the user's first genuine human labels.** A real historical 30-task development batch is present on this machine, and the authenticated page is accessible from the Stock Radar 4174 sidebar. This does not say that a Box model has been trained or that any pattern predicts returns. The branch is not approved for merge to `main`.

## Exact implementation and data boundary

- Frozen source: `shape_research_universe_v1` with RI v1 semantic hash `74b765911a8a4f18b2074cd8d9e529b25b54afade15309a148b0ca43340b80be`. `BoxHistory` uses the supported 126-session decision window, then reads at most 1,100 earlier same-series, same-source, same-basis, research-ready sessions from the frozen core. No frozen code/database was edited.
- Decision domain: Train 2021-09-01–2024-08-29; Validation 2024-09-30–2025-09-08. No Test or Fresh tasks.
- Candidate plugin: isolated pure `loose-box-v1`; descriptors use robust band width, containment, turning points, drift, position and undercut. The explicit initial thresholds live in `config/box_labeling_v1.yaml`; they were selected for permissive retrieval, not tuned against future outcomes.
- Deterministic sampling seed `20261011`: ~70% prefilter positive, 20% near miss, 10% periodic unconditional historical control. Stratum, diagnostics and score stay in the private manifest and are absent from the human HTTP payload. One security per batch avoids overlapping same-security Train/Validation windows.
- Numerical input and human view after the user's 2026-10-11 window correction: daily 42 trading sessions (about two months), weekly 52 bars (one year), monthly 48 bars (four years) when available. Final incomplete week/month ends at the observed T session. No forward filling. Missing-length scales have explicit masks and the page states actual coverage. Prices use `log(OHLC/T_close)`; volume uses `log1p(volume)/log1p(past-scale median volume)`. Raw dated OHLCV, normalized `.npy`, SVG and SHA-256 hashes are kept separately. SVG pixels never enter model X.
- Human label schema `box-structure-label-v1`: shape BOX / NOT_BOX / UNCERTAIN; position LOWER / MIDDLE / UPPER / BREAKDOWN / UNCERTAIN; confidence HIGH / MEDIUM / LOW; finite optional reasons and short note. Existing Label Studio authentication/session/CSRF are reused. Separate `annotations-human.sqlite3` and `annotations-smoke.sqlite3` keep tests away from Ground Truth. SQLite append-only revisions and expected-revision compare-and-swap block silent overwrite.
- Export is numeric only. It validates saved tensor hashes, joins the latest human revision to local `.npy` references, retains private ID/split and rejects a security that appears in both Train and Validation. No future-return field, SVG or candidate score is exported. The optional small PyTorch 1D CNN has three sequence encoders, scale masking and separate shape/position heads; its only fit so far used synthetic fixture labels.

## Actual local run

Private current batch: `data/box-label-v1-2m-1y-4y/` (Git ignored); 1,800 deterministic eligible rows loaded into the candidate pool, 34 evaluated before the quotas filled (27 natural positive, 7 natural boundary). Selected:

| Stratum | Count |
|---|---:|
| Prefilter positive | 21 |
| Boundary / near miss | 6 |
| Unconditional control | 3 |

30 tasks represent 30 unique historical security IDs. Train 21 / Validation 9; 2022: 8, 2023: 8, 2024: 7, 2025: 7. Membership recorded as 23 `confirmed_member`, 7 `probable_member`, zero unknown. Sources: 29 legacy Alpaca SIP split-basis, 1 Dolt raw-basis, each bound by the frozen safe-window checks. Daily has 42 bars for all 30; full 52-week coverage for 22; full 48-month coverage for **6**. The frozen database begins 2021-09-01, so Train-period tasks cannot possess four earlier years. Shorter history is shown honestly (e.g. 12/48 monthly bars) and masked rather than invented. Seven 2025 Validation decisions were selected from August/September to provide some full four-year examples without removing the earlier Train years. The batch is intentionally small and selected; it cannot establish complete-market recall. Disappeared-security participation in this specific 30-task draw was not separately proven, and RI v1's documented disappeared-security coverage limits still apply.

Config SHA-256: `4d78b209a077d8f4fb2722d103f4750940f1c690a8f1051a98b726152fa8a766`. Private manifest SHA-256: `a48d701967e765846233af4a8987ccde28b2842c77a8eada942a2725c6e8425d`. Renderer `box-three-scale-svg-v1`, numeric normalization `box-numeric-ohlcv-v2-42d-52w-48m`. The offline verifier reopened all 30 tasks, recalculated tensors from raw OHLCV, rerendered each of 90 SVGs, checked every hash and required every scale to end exactly at T. Result: PASS.

## Browser and persistence evidence

- `http://localhost:4174/lab.html#lab` served the new sidebar link. Clicking **Box Labeling** navigated in the same browser tab to `http://localhost:8124/box-label/v1/human/` using the existing Label Studio login session. The human page showed 1/30 and three real historical candle images with blank labels.
- The isolated `/box-label/v1/smoke/` route was visited in the real in-app browser. Ten distinct **new-window** tasks (1–10) were checked; all three SVGs loaded on each. The UI displayed actual bar counts, including 48/48 monthly on tasks 4 and 8 and shorter available histories on earlier tasks. BOX, NOT_BOX and UNCERTAIN; LOWER, MIDDLE, BREAKDOWN and UNCERTAIN; HIGH/MEDIUM/LOW; a reason checkbox; save, skip, next/previous and revision were exercised. Unsaved undo was verified on the prior window batch and remains the same UI code.
- One task was edited from revision 1 to revision 2. Refresh and return showed revision 2 with the new values. The current-window smoke numeric export produced 3 examples, loaded by `trainer.load_export` (SHA-256 `6abbfc0ee4b8d82731b9aafa12a22ed22ce8d14703ab74ba81f88ff18f360cf5`); the smoke DB retained 4 revision rows. The human annotation DB retained **0** rows.
- Anonymous access to `/box-label/v1/human/` redirected to the existing Label Studio login. The human payload has only task ID, three SVGs, scale coverage, revision/current label and label version; no date, symbol, security ID, stratum, score or future Y. The 8124 startup disables Label Studio's optional PyPI version check and Sentry telemetry.

## Automated gates

- Targeted causal/contract suite: **8 passed**. Covered post-T mutation invariance of plugin result/tensor/render hashes, partial week/month cutoff, price-rescaling invariance, candidate input isolation/determinism, visible-payload isolation, smoke/human separation, validation of label choices, compare-and-swap revisions, numeric export loading, split-overlap rejection, raw-hash drift, real RI v1 provider boundary and a synthetic-only checkpoint smoke.
- Entire project `pytest -q` in the existing project virtual environment after the final 42/52/48 window change: **719 passed, 17 skipped, 1 warning** (the existing `websockets.legacy` deprecation warning). No failed tests. Native LEAN profitability execution was not invoked because this work order forbids portfolio backtesting.
- PyTorch CPU `2.14.1+cpu` synthetic-only smoke: one optimizer step completed; shape logits `[8,3]`, position logits `[8,5]`. These fixture metrics say nothing about real model quality.

## Remaining boundary

The user has not yet supplied any genuine box-structure labels. Formal human Ground Truth, supervised model quality, future-outcome evaluation and profitability remain **NOT_RUN**. Candidate selection bias remains; only the small unconditional control channel offers a check on what the prefilter misses. Production model training requires enough real labels and a separate authorization. The code should be reviewed in a PR, then merged only on explicit approval. Old Q1/Q2 runs, v3 labels and frozen RI v1 artifacts remain untouched.

# Box numeric partial-history mask repair — 2026-10-13

## Decision

**Engineering fix verified in draft PR #21.** This is a follow-up to the dated Box Labeling v1 acceptance; its original 2026-10-11 receipt is unchanged. No real human model was trained.

## Defect and change

The existing numeric export records both the true observed length and `available`, where `available` means *full target window*. `load_export()` previously passed only `available` into the model. Consequently a valid 12/48 monthly history received a zero scale embedding even though 12 real bars existed. The same defect affected any partial weekly scale.

The loader now validates observed length against the actual tensor and full-coverage flag, then passes integer lengths to a versioned `multi-scale-1d-cnn-v2-length-masked` scaffold. Each convolutional stage clears padded positions; pooled embeddings average only observed steps. A zero-length scale produces a zero embedding. The existing v1 `.npy`, raw OHLCV, chart artifacts, manifest and human annotation schema are unchanged. Older v1 checkpoints are not interchangeable with the v2 architecture.

## Verification

- Focused `tests/test_box_labeling_v1.py`: **9 passed**. The new test uses a genuine partial-length numeric fixture and confirms its encoder embedding is nonzero, arbitrarily changing padded values leaves that embedding unchanged, zero observed length yields zero, and an incorrect exported length is rejected.
- Full project `pytest -q` with the existing Windows project virtual environment: **720 passed, 17 skipped, 1 warning** in 49.73 s. The warning is the existing third-party `websockets.legacy` deprecation.
- `git diff --check` and Markdown/privacy scope review are required before publishing the PR update.

## Scope boundary and next step

This repair closes the known partial-scale representation defect. It does not resolve the separate 126-session candidate selector versus 42-session close-up display design choice, extend scarce four-year historical coverage, produce genuine human labels, validate detector recall or authorize real supervised training. The reviewed next-path proposal is in PR #23; `codex/tasks/ACTIVE.md` still points to Box Labeling v1.

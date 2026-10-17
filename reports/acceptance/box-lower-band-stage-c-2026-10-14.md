# Box Range Stage C local acceptance — 2026-10-14

**Engineering diagnostic complete; formal structure and return validation
remain unverified.** The owner cancelled mandatory blind human review and
authorized autonomous continuation. No AI/smoke label was counted as human
Ground Truth; the previously frozen 48-task set and human store remain intact.
Earlier Stage B acceptance is preserved as dated evidence.

## Implementation and real data

- A versioned, T-only lower-band context consumes the exact Stage A detector
  scan. It rejects mismatched history, detector config, date, identity, source,
  basis and RI semantic hash. States and reason codes separate structure,
  current location, recent stabilization, extension and volume context.
- The fixed 48 Train/Validation security-days (12 per year, 2022–2025) were
  processed through frozen RI v1. No outcome, label store, Test or Fresh rows
  were read. The immutable private row-level receipt has SHA-256
  `88e3449deaaa8a1ee74cfdf1ac0d6bdf7132adb2a984e7d3609c6ae8f18e00c3`.
  Only aggregate counts are committed in the [evidence JSON](../evidence/box-lower-band-stage-c-2026-10-14.json).
- Quantile detector: 34 no active range, 9 away from lower zone, 3 undercut,
  1 price wait, 1 near-lower stabilizing. Confirmed-pivot detector: 46 no
  active range, 1 away, 1 undercut. Neither detector was selected by an
  outcome or by treating the other's output as truth. These small counts are
  coverage/context only; no precision, recall, win rate or alpha follows.
- All 48 identities are still observational; 12 have retrospective C-level
  provenance flags. The prior read-only timing audit narrowed those flags but
  did not establish official issuer continuity. No frozen RI v1 row or
  protected Strategy 2 parameter was changed.

## Tests and boundaries

- Focused Stage C tests: **6 passed**. Causal input binding, future-row
  rejection, post-T mutation invariance, no-active-range and versioned config
  were checked with synthetic controls.
- Full default pytest: **759 passed, 18 skipped, 1 warning** in 52.74s.
- Full pytest with `STOCK_RADAR_TEST_LEAN=1`: **769 passed, 8 skipped,
  1 warning** in 96.43s. Native LEAN regression was exercised; no new Stage C
  portfolio backtest was run. The warning is the installed `websockets.legacy`
  deprecation.

The blind sample was drawn without regard to detector output and is too small
to estimate market-wide opportunity frequency. No human review now blocks
engineering, per owner decision, but there is **no independent structure
accuracy measurement**. The next research step needs issuer provenance and a
separately frozen execution/outcome contract before formal local LEAN claims.

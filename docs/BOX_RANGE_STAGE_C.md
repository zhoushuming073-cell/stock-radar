# Box Range Stage C — lower-band context

The owner cancelled mandatory human blind review on 2026-10-14. The blind
48-task pool and Label Studio route are preserved as optional research assets;
they are not used by this module. No structure-accuracy rate is available.

`src/radar/box_labeling/lower_band.py` takes one versioned `RangeScan` and the
exact OHLCV prefix through T. It rejects a changed input, config, date, source,
basis, security ID or RI semantic hash. It uses the detector's single
`best_active` confirmed range, without combining the two algorithms or choosing
a box using later prices. The returned state is one of:

- `NO_ACTIVE_RANGE`: no confirmed active detector range at T;
- `WAIT_UNDERCUT`: T close remains below the geometric floor;
- `AWAY_FROM_LOWER`: T close is above the configured lower third;
- `WAIT_PRICE`: too little room to the upper zone or recent price extension;
- `WAIT_STABILIZATION`: recent decline, missing volume baseline or exceptional
  volume needs observation;
- `NEAR_LOWER_STABILIZING`: preliminary T-only context, **not** a buy signal.

All thresholds live in `config/box_lower_band_context_v1.yaml`. They are
explainable initial bounds, not optimized estimates. The minimum 8% room to
the resistance zone is a conservative geometric buffer around the research
idea of a partial 5% internal swing. The 6% single-day and 10% three-day
extension checks avoid labeling an already rebounded close as near entry. A
last close down more than 0.5% or a three-day low more than 2.5% below the
preceding three days is treated as not yet stabilized. A three-day volume
ratio above 4 is a review flag, not proof of buying or selling pressure.

Read-only local diagnostic (private output path must not exist yet):

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
..\stock-radar\.venv\Scripts\python.exe -m scripts.audit_box_lower_band_stage_c `
  --research-root ..\stock-radar `
  --selection ..\stock-radar\data\box-range-stage-b\blind-selection-v1.json `
  --expected-selection-sha256 f64acf27893960ed3ac449d398a89bf0cdf4396d170c6669e8ab5043644f15a5 `
  --output ..\stock-radar\data\box-range-stage-c\another-immutable-local-run.json
```

The actual 2026-10-14 run and test counts are in the [Stage C acceptance
report](../reports/acceptance/box-lower-band-stage-c-2026-10-14.md). The 48
rows are a fixed, small, unstratified historical audit sample. They are not
the eligible-market denominator, do not establish accuracy or returns, and
do not justify threshold tuning. All selected identities remain observational
under frozen RI v1; formal outcome/LEAN work requires an independently trusted
execution population and a separate frozen rule contract.

The [subsequent as-of-T issuer-alias audit](../reports/acceptance/box-range-issuer-alias-asof-t-2026-10-14.md)
found four contemporaneous same-CIK aliases and one known name conflict in the
48-row sample. Those five rows are isolated from later exploratory analysis;
the other 43 still have observational, not official, identity provenance.

The [T+1 metadata preflight](../reports/acceptance/box-execution-metadata-preflight-2026-10-14.md)
finds source/basis-matched research rows for all 43. This is one-session
coverage, not an executable price or local LEAN acceptance.

The [10-session metadata audit](../reports/acceptance/box-execution-horizon-metadata-2026-10-14.md)
stays within Train/Validation and reads no future OHLCV. It finds only 20 of
430 later sessions with same-source raw rows; only 2 of 43 diagnostic tasks
have a complete unflagged raw horizon. This is the immediate execution-data
gap. Split-adjusted box-research bars cannot substitute for the native LEAN
raw price/action closure.

The downstream [Stage D daily context scanner](BOX_DAILY_SCAN_STAGE_D.md)
now has a real one-day acceptance with immutable private chunks and explicit
remaining historical coverage. It remains research context, not a strategy
order stream or LEAN result.

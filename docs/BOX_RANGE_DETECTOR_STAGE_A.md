# Box RangeDetector — Stage A engineering contract

> 2026-10-13 · Quant-only structure research. This branch is stacked on unmerged
> PR #24 → PR #21. The revised research route is in documentation PR #23.
> No human Ground Truth, future outcome, strategy entry or LEAN result is used.

## Interface and causal boundary

`src/radar/box_labeling/range_detector.py` defines one `RangeDetector` protocol and
two independent baselines: `quantile-zone-v1` and `confirmed-pivot-zone-v1`.
Both consume exactly `date, open, high, low, close, volume` through decision
close T. Full frames containing post-T rows, extra columns, duplicate/unsorted
dates, non-finite values or invalid OHLC are rejected. The production research
caller is the existing read-only `BoxHistory` / Research Infrastructure v1,
which enforces dated membership, homogeneous source/basis, contiguous trusted
sessions and the protected Train/Validation domain.

Config `box-range-detector-stage-a-v1` is hashed and bounded to 126 daily
sessions. It searches completed 42/63/84/105/126-session windows ending every
five sessions and at T. A window ending before T uses only bars through that
window for its geometry; later bars through T determine its **current state**
separately. `formation_start`, `window_end`, `first_knowable_at`, and pivot
`event_date`/`first_confirmable_at` are separate fields. The conservative
`first_knowable_at` for a complete-window diagnosis is its window end. It
does not claim the same visual range could not have been noticed earlier.

The returned `RangeScan` records source/basis and RI semantic hash, input and
config hashes, candidate diagnoses and rejection counts across bounded windows, the best
historically confirmed range, the best **currently unbroken** range, and
`NONE | DEVELOPING | CONFIRMED | BREAKDOWN | UNCERTAIN` at T. An expired
historical range remains in `structure_exists_in_past` but cannot become an
active range or an indefinitely current breakdown. An upper break, one-session
undercut, recovered false undercut and sustained lower break have different
state/evidence. Detector disagreements are preserved.

The quantile baseline derives candidate zones from low/high 12th/88th
percentiles, then requires independent side touches, alternations, occupancy,
width and limited center drift. Its touch is classified against a band only at
the window end. The pivot baseline reuses SciPy `find_peaks` to find single-bar
local extrema, then computes prominence within a strictly bounded symmetric
three-left/three-right window. No full-series prominence or distance filter
may remove/confirm an earlier pivot using later peaks. Zones are robust medians
of pivot levels; outliers are excluded before touch/alternation checks. A
pivot's first confirmation is three completed right-side daily bars after its
event. These thresholds are explainable starting values, not trained or
future-return-optimized parameters.

## Open-source decision receipt

| Component | Inspected source / state | Stage A decision |
| --- | --- | --- |
| [NumPy quantile](https://numpy.org/doc/stable/reference/generated/numpy.quantile.html) | Existing project dependency; local test environment NumPy 2.5.3 | Use for transparent quantile baseline |
| [SciPy `find_peaks`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.find_peaks.html) | [SciPy repository](https://github.com/scipy/scipy), BSD-3-Clause; local Windows/Python 3.13 wheel 1.18.1 installed and tested | Use behind `box-detector` optional dependency; causal local swing wrapper is Radar-owned |
| [trendln](https://github.com/GregoryMorse/trendln) | MIT, inspected `82dcb119a667f1a1ef5dd8e5a55624236e56973d`; its setup declares Python ≥3.10 and NumPy/findiff/scikit-image/Pandas/Matplotlib | Possible later line adapter; additional stack and line-selection semantics need isolated tests; not installed or copied |
| [pytrendline](https://github.com/ednunezg/pytrendline) | MIT, inspected `d575f958818089a41e669262ae843e287251d072`; README describes O(N³) exhaustive line search and older plotting dependencies | Bounded tilted-line comparator later; no universe-wide adoption before benchmark |
| [support_resistance](https://github.com/day0market/support_resistance) | Inspected `fdd4a7f0fdccf6c4007da79fd6f3879164462c3c`; GitHub metadata declares no license; requirements pin NumPy 1.17/Pandas 0.25/SciPy 1.3 and ZigZag 0.2.2 | Ideas only; no source copying or installation |

These repository/license/dependency observations are dated checks, not a
compatibility or accuracy guarantee. No proprietary charting-system code or
outputs are part of this implementation.

## Local diagnostic invocation

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
..\stock-radar\.venv\Scripts\python.exe -B scripts/audit_box_range_detector_stage_a.py --research-root ..\stock-radar --per-year 24
```

The script reads only frozen Train/Validation 126-session eligible rows and
prints aggregate year/membership/source counts, exclusions, output states,
disagreement and elapsed times. It prints no security ID, exact decision date,
price row, image, annotation or future outcome. The source checkout path is
configurable. The committed [aggregate receipt](../reports/evidence/box-range-detector-stage-a-scan-2026-10-13.json)
is **diagnostic coverage/runtime only**; hash-draw security-days are not an
independent labeled set. Its first-call SciPy import can inflate max latency.

## Known limits and next gate

- Quantile and pivot outputs disagree substantially on the small real sample;
  neither is validated as a true box detector. Retain raw disagreements.
- Searching only five lengths and every fifth end within 126 sessions can miss
  shorter, longer or differently timed structures. Stage B must measure this.
- Zones and status are heuristics; subtype, gentle slope, issuer continuity and
  formal source/basis reconciliation need Stage B review. The detector does not
  produce trade signals, executable prices or profitability claims.
- The frozen historical source has missing disappeared-security/identity
  coverage. The sample denominator is eligible **indexed** security-days,
  not the full US market.
- Next: follow the six unverified Alpaca reference cases **plus** a separately
  frozen blind historical audit set under the Stage B protocol in PR #23.
  No old band/date is a detector target; POET's four-day window is an active
  state check only. Genuine human structure review, data-basis reconciliation
  and error analysis require a later authorization.

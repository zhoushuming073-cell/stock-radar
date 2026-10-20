# Box RangeDetector Stage A — local engineering acceptance

**Date:** 2026-10-13 · **Result:** **ENGINEERING PASS / STRUCTURE ACCURACY NOT VALIDATED**.
This report records actual local execution on the dependent Stage A branch
based on PR #24 head `b8cd299f33ef2ba9362962b965f08e7bd6e71c85`.
PR #24 depends on unmerged PR #21. The route specification is in PR #23.
No implementation PR is merged into main by this receipt.

## Delivered and verified

- One typed `RangeDetector` protocol and versioned `RangeConfig` /
  `RangeScan` contract. Two independent baselines: NumPy quantile zones and
  SciPy `find_peaks` with strictly local, delayed-confirmation pivot evidence.
- Bounded 42/63/84/105/126-session searches in a 126-session T-prefix.
  `formation_start`, `window_end`, `first_knowable_at`, touch
  `event_date` and `first_confirmable_at` are distinct. Historical confirmed
  structure and active unbroken status at T are distinct; expired structures
  cannot be current breakdowns.
- Input rejects future rows, extra columns, duplicate/unsorted dates,
  non-finite and invalid OHLCV. The actual scan uses `BoxHistory`, the
  read-only RI v1 research API, for supported membership, trusted contiguous
  sessions and one source/basis per history.
- `loose_box_v1`, original annotation stores, CNN scaffold, frozen Strategy 2
  and frozen RI v1 database were not modified. No labels, Y outcomes,
  Historical Test/Fresh, LEAN/QC or return calculations were read or run by
  the detector scan.

The starting thresholds are documented in
[`config/box_range_detector_stage_a_v1.yaml`](../../config/box_range_detector_stage_a_v1.yaml).
They were chosen for interpretable geometry, not fit to these securities or
future returns. See the [engineering guide](../../docs/BOX_RANGE_DETECTOR_STAGE_A.md)
for open-source due diligence and interface limits.

## Real historical diagnostic receipt

Command (Windows, with current branch `src` on `PYTHONPATH`):

```powershell
..\stock-radar\.venv\Scripts\python.exe -B scripts/audit_box_range_detector_stage_a.py --research-root ..\stock-radar --per-year 24
```

[Machine-readable aggregate receipt](../evidence/box-range-detector-stage-a-scan-2026-10-13.json)
contains no ticker/security ID, exact decision date, OHLCV row, chart or
annotation. The script's SQL includes only frozen Train/Validation dates,
supported membership, `shape_research_ready` and a 126-session index; it
does not join outcomes or today's listing status.

| Item | Actual observation |
| --- | ---: |
| Eligible indexed security-days, 2022 / 2023 / 2024 / 2025 (2025 through Validation 2025-09-08) | 680,566 / 830,719 / 854,897 / 665,376 |
| Eligible indexed total | **3,031,558** |
| Fixed-hash diagnostic draw | 24/year; **96 security-days**, 95 distinct security IDs |
| Supported membership in draw | 85 confirmed / 11 probable |
| Provider safety exclusions | 0 of 96 |
| Historical price source/basis in draw | 90 `legacy:alpaca:sip / split`; 6 `Dolt:post-no-preference/stocks / raw` |
| Windows evaluated per detector | 4,416 |
| Different T-state outputs between detectors | **69/96** |
| Quantile historical structure / active at T | 81 / 38 security-days |
| Pivot historical structure / active at T | 18 / 5 security-days |
| Quantile median / p95 / max elapsed per security-day | 36.88 / 46.59 / 61.14 ms |
| Pivot median / p95 / max elapsed per security-day | 26.88 / 35.49 / 930.90 ms |

The pivot maximum includes first-call SciPy import. Timings describe this
machine/run, not portable latency guarantees. The 96 sampled security-days
are an engineering diagnostic, not an independent set of 96 confirmed boxes.
Some windows overlap and one security appears twice. The 3,031,558 denominator
is the frozen **eligible indexed** history in these bounded dates, not all US
security-days. Supported membership excludes unknown; disappeared-security
and missing-history limitations remain. No detection percentage above is a
precision, recall or predictive lift statistic.

RI semantic hash:
`74b765911a8a4f18b2074cd8d9e529b25b54afade15309a148b0ca43340b80be`.
Config hash:
`bedd4815553e73a866594c735dda89eb3dba559b704f3772c167d2a856af3f1e`.
Detector source SHA-256 at receipt:
`65e268eb647abda244f5bebaf8ce32bada6f4e175f0917f88e26f402f9292321`.
The source/config file SHA-256 values normalize CRLF to LF across checkouts.
The source commit hash is recorded by the later PR; these three hashes bind
the local diagnostic to its RI semantics, configuration and implementation.

## Regression

- Targeted detector tests: **22 passed**. They cover real oscillating
  structure, monotonic trends, crash/breakdown, stale expiry, strict input
  rejection, future mutation, pivot right-bar delay, long-plateau rejection,
  price-rescale invariance and visible baseline disagreement.
- Full command:
  `$env:STOCK_RADAR_TEST_LEAN='1'; ..\stock-radar\.venv\Scripts\python.exe -B -m pytest -q` using the existing local
  project virtual environment: **754 passed, 8 skipped, 1 warning** in
  **96.25 seconds**. The Native LEAN opt-in flag was set; its local installation
  was present and the native integration tests were included. The warning was
  the existing `websockets.legacy` deprecation.
- No real human label, model training or actual Stage B six-stock structure
  judgment was performed.
- The local Python 3.13 environment used SciPy 1.18.1; `pip check` reported
  no broken requirements after installing the optional detector dependency.

## Decision and remaining risks

Stage A engineering is accepted as an interpretable detector **foundation**.
The 69 disagreements make Stage B independent blind review essential. The
quantile method is intentionally permissive and may call weak one-sided
oscillations a range; the pivot method is more selective and may miss noisy or
tilted boxes. Neither was tuned on the familiar IREN/RIOT/APLD/SOFI/IONQ/POET
cases. Those old windows remain unverified candidates; POET's four-day window
is only a 2026-10-12 active-state check. Historical source/basis differences
from the user's Alpaca SIP verification are still unreconciled.

Stage B requires a separately authorized protocol: keep the six familiar
cases as diagnostics, freeze a separate time/issuer-blind historical audit
set, get genuine human structure judgments, reconcile price/corporate-action
basis, and report misses, false positives, state and boundary errors with
denominators. No lower-band trading rule, outcome study, Test/Fresh or LEAN
backtest is authorized by this engineering PASS.

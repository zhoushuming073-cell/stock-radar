# Box execution horizon metadata audit — 2026-10-14

**Result: research-price metadata spans the sampled 10-session horizon, but
same-source raw execution data does not. Formal box LEAN backtesting remains
blocked.** This is a read-only data audit, not an outcome study or a trading
result.

The script binds the frozen Stage B selection and T+1 preflight by SHA-256,
checks the Research Infrastructure v1 semantic hash and the frozen Train and
Validation boundaries, then enumerates up to 10 later sessions **within the
same split**. It queries `shape_price` for source, basis, readiness, identity
and action flags. It never reads later OHLCV values, returns or labels. Rows
from Historical Test and Fresh OOS are not queried. The 10-session extent is
only a coverage diagnostic; no strategy holding period has been selected.

| Check on 43 observationally conflict-free Stage B samples | Actual result |
| --- | ---: |
| Expected and enumerated post-T sessions | 430 / 430 |
| Tasks with all 10 matched-basis sessions unflagged | 42 / 43 |
| Tasks with all 10 same-source raw sessions unflagged | 2 / 43 |
| Session rows with one same-source raw version | 20 / 430 |
| Session rows with a raw version from any source | 199 / 430 |
| Missing or ambiguous same-source raw session rows | 410 / 430 |
| Matched-basis action flag / not research-ready | 1 / 1 |
| Tasks censored by a Train/Validation split end | 0 |

The one flagged row is an aggregate count, not a public security/date mapping.
An alternative raw row from a different source is **not** silently substituted
for the source fixed at T. The 41 split-basis T+1 cases seen in the earlier
preflight remain split-adjusted research observations. Their future values
cannot be fed to the existing raw-price LEAN path as executable Open prices.
Nor does a same-source raw row alone certify the factor, map, cash action,
terminal settlement, order-fill or benchmark closure that LEAN requires.

Private per-task dates, identities and metadata remain in ignored local
`data/box-range-stage-c/execution-horizon-metadata-v1.json`, SHA-256
`a0e777da8938b469363f14d1a320daf7a843c6c41412aa6d8a181b6e17d2a381`.
Only the [aggregate evidence](../evidence/box-execution-horizon-metadata-2026-10-14.json)
is committed. The diagnostic is based on a 48-task nonrepresentative pool,
with 5 known alias/name-risk rows excluded. No market-wide raw coverage rate
or expected strategy return follows from these counts.

## Next execution boundary

1. Build a dated, resumable Train/Validation daily signal stream for each
   detector **separately**. Keep the detector versions and lower-band config
   fixed; record every eligible denominator and exclusion. Do not treat this
   sample's near-lower frequency as a market-wide estimate.
2. Construct an independently verified as-of-T issuer/alias map and a frozen
   raw execution-price dependency closure covering the full possible holding
   period. The current `radar.pit.execution` path requires raw prices, corporate
   actions, symbol maps and terminal treatment; do not bypass its gates with
   split-adjusted research prices or a different-source raw row.
3. Freeze an explicit entry, ranking, sizing, exit, fee, slippage and portfolio
   contract before looking at returns. The present Stage C state is context,
   not an order. Compare the two detector variants independently on Train and
   Validation first. Do not use Test/Fresh to choose rules.
4. Only after these inputs pass should a local Native LEAN portfolio run be
   considered. The existing LEAN adapter and normalized Stock Radar UI remain
   the execution and presentation route; no second engine is needed.

The immediate outcome/LEAN protocol is therefore **fail closed**. No formal
profitability, detector accuracy or run-readiness claim was made. Focused
horizon tests: **3 passed**. Full project pytest with
`STOCK_RADAR_TEST_LEAN=1`: **776 passed, 8 skipped, 1 existing
`websockets.legacy` warning** in 98.99 seconds. Native LEAN regression was
enabled; no new box portfolio run occurred.

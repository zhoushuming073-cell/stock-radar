# Box near-lower candidate execution-metadata audit — 2026-10-14

**Result: the raw execution-price gate remains open on both complete
candidate days.** The existing 43-task diagnostic had shown a gap; this
follow-up checked all 242 near-lower contexts from one complete Train and one
complete Validation day. It did not read subsequent OHLCV values, returns,
orders, fills, human labels, Test or Fresh data.

Each private candidate receipt was reverified against its frozen eligible
population, selected set, code/config/RI hashes and immutable file-set hash.
The existing split-bounded `horizon_metadata` implementation then inspected
only session presence, source/basis, readiness, identity and action flags for
up to ten later trading sessions. **Ten sessions is a data-coverage diagnostic,
not a chosen holding period.** No candidate became a trading signal.

| Actual candidate day | Train 2024-07-01 | Validation 2025-06-02 |
| --- | ---: | ---: |
| Near-lower candidates | 96 | 146 |
| Expected/observed later sessions | 960 / 960 | 1,460 / 1,460 |
| Complete matched research-basis metadata | 95 | 144 |
| Complete unflagged same-source raw metadata | **18** | **11** |
| Individual sessions with one same-source raw row | 180 | 119 |
| Individual sessions with raw from any source | 960 | 1,451 |
| Split-censored candidates | 0 | 0 |

Together, only **29/242** candidates have a complete, unflagged same-source
raw metadata horizon; only **299/2,420** later candidate sessions have one
same-source raw row. Alternative-source raw rows are much more frequent on
these dates, but cannot be silently substituted for the source fixed at T.
Matched split-adjusted research rows also cannot be treated as tradable Open
prices. Even the 29 metadata-complete cases still lack formal issuer,
corporate-action/factor, terminal settlement, benchmark and portfolio-rule
closure. This audit does not certify 29 LEAN-ready signals.

The private candidate/session/identity maps are stored only in ignored local
`data/box-range-stage-d/execution-metadata-candidates-v1`. Their SHA-256
values were independently re-read and matched the output receipts. Only the
[aggregate evidence](../evidence/box-candidate-execution-metadata-2026-10-14.json)
is committed. These two dates do not estimate all-history raw availability;
the ongoing historical candidate backfill has not completed. The result
explains why a formal box portfolio backtest remains blocked without
weakening existing PIT/LEAN gates.

Focused candidate/horizon tests passed. Full regression result is below.

## Regression

Focused candidate/horizon tests: **5 passed**. Full project pytest with
`STOCK_RADAR_TEST_LEAN=1`: **790 passed, 8 skipped, 1 existing
`websockets.legacy` deprecation warning** in 123.01 s. Native LEAN regression
was enabled; no box portfolio run occurred.

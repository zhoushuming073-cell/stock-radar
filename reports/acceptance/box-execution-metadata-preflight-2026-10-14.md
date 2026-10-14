# Box T+1 execution metadata preflight — 2026-10-14

**Result: T+1 metadata is present for the 43 observationally conflict-free
diagnostic rows; formal LEAN execution remains unverified.** This is a read-only
preflight, not a box strategy backtest or an outcome study.

The checker verifies the SHA-256 and private task/identity/date joins of the
frozen Stage B selection, Stage C detector-context receipt and subsequent
issuer-alias receipt. It excludes four contemporaneous CIK aliases and one
known name conflict. For each remaining T it finds the next session in frozen
RI v1 and examines only source, price basis, readiness, identity, split and
membership metadata. It does not select or read future OHLCV values.

| T+1 metadata check | Result |
| --- | ---: |
| Observational rows checked | 43 |
| Exactly one next bar matching T's source and basis, with ready flags | 43 |
| Also had an alternative source or price basis row | 17 |
| Matching next basis: raw / split | 2 / 41 |
| Stage C near-lower state: quantile / pivot | 1 / 0 |

An initial query counted all source/basis rows and incorrectly reported 17
duplicate next bars. The corrected query filters by the source and basis
frozen at T. An in-memory test checks that an alternative raw row is not a
duplicate of the selected split row and that a missing matching basis fails
closed. The abandoned first private output is retained as an audit trail;
the corrected immutable private receipt has SHA-256
`343ed24ee1c9ac557274becb8a4b9a623144e01bffb4c8d2a3708d4a9526966d`.
Only the [aggregate evidence](../evidence/box-execution-metadata-preflight-2026-10-14.json)
is committed.
Focused preflight tests: **2 passed**. Full pytest with
`STOCK_RADAR_TEST_LEAN=1`: **773 passed, 8 skipped, 1 existing
`websockets.legacy` warning** in 98.38s. Native LEAN regression was enabled;
no new box portfolio run occurred.

This check covers **one next session** and only a 48-row diagnostic sample,
not a full historical signal stream or the holding horizon. It does not
certify absolute executable Open prices, split/dividend factors, delisting
settlement, fill realism, SPY benchmark coverage or a LEAN result. The 41
split-basis rows especially require a coherent corporate-action/factor
contract before an execution claim. Issuer identity remains observational;
the rules for choosing between highly disagreeing detectors, position sizing,
exit and invalidation remain unfrozen. Those are separate Stage D gates. No
future return, label, Test/Fresh result or portfolio outcome was read here.

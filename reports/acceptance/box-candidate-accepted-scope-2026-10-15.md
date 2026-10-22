# Why 982 box candidate-days are absent from the accepted PIT price table — 2026-10-15

**Result: all 982 candidate-days with no accepted T-day price row are within
the older PIT research dependency; all 982 fail that closure's retrospective
`research_identity_pass` gate.** The missing *accepted* rows must not be
reported as 982 missing raw market-data rows. The accepted table was built
only from dependency records that passed its whole-closure research identity,
material-risk and source-disagreement rules. This audit did not establish
whether a raw row exists for each of the 982 private ID/date pairs.

The read-only `box-candidate-acceptance-scope-v1` auditor reruns the
[77-session Validation-prefix T-day bridge](box-candidate-prefix-tday-2026-10-15.md)
and rechecks the 580-file candidate set, accepted database and frozen
`identity-risk.json` SHA-256 against its manifest. It joins the same private
security ID to the prior PIT risk scope, then publishes **aggregate counts
only** in [the evidence](../evidence/box-candidate-acceptance-scope-2026-10-15.json).
No private identity or price row is committed.

| Accepted T-day status or older PIT scope | Candidate-days |
| --- | ---: |
| Dolt/raw candidate-days in sealed Validation prefix | 1,531 |
| Exact accepted T-day match | 549 |
| No accepted T-day row | 982 |
| Missing row outside the older PIT dependency | 0 |
| Missing row inside dependency, rejected by whole-closure gate | 982 |
| Of the 982: retrospective identity level C / B | 812 / 170 |
| Of the 982: material review also required | 847 |

The older PIT identity reasons overlap. Among the 982 missing accepted
candidate-days, the retrospective risk file lists material
lifecycle/action evidence for 654, multiple observed ticker identity
episodes for 196, ADR/share-class/lifecycle ambiguity for 95, and
unexplained price continuity for 170. These reason counts must not be
summed as distinct candidates. All 982 have `research_identity_pass=false`
in that file, so its acceptance rule excludes them regardless of whether
the raw T-day price might be available.

**Causality boundary:** the older `identity-risk.json` evaluates a full PIT
research closure and may include evidence first available after a candidate's
decision date. This audit uses it solely to explain why the old accepted
database omitted rows. It does not change the Stage D candidate set, label
the 982 as bad T-day structures, or use retrospective flags as a historical
selection rule. The older `research_identity_pass` also considers price
continuity; it is not a pure legal issuer certificate. Separate as-of-T
issuer, raw-price/action/factor and execution gates remain open.

The actual local audit produced the linked aggregate evidence. Focused
scope/T-day bridge tests: **5 passed**. Full-project regression ran with
`STOCK_RADAR_TEST_LEAN=1`, including Native LEAN fixture tests.

**Regression: 813 passed, 8 skipped, 1 existing `websockets.legacy`
deprecation warning.** No box portfolio backtest ran.

No Test/Fresh, future OHLCV values, future returns, human labels or box
LEAN backtest were used. The immutable Train/Validation candidate workers
were not changed or stopped. Formal LEAN remains blocked.

# Box candidate Validation-prefix issuer observations at decision T — 2026-10-15

**Result: the older PIT accepted-price table's whole-closure exclusion and
decision-dated issuer observations answer different questions.** Of 982
Dolt/raw candidate-days missing an accepted T-day row, 876 have no *known*
issuer conflict in the existing T-dated construction evidence, while 106
have an observed risk. This does **not** certify any of the 876 as a legal
issuer or make them executable. The older accepted table's full-window
identity rejection must not be used as a historical T-day candidate filter.

The `box-candidate-prefix-issuer-asof-t-v1` read-only auditor first reruns
the [full-prefix T-day price bridge](box-candidate-prefix-tday-2026-10-15.md),
which hash-verifies all 580 immutable chunks from 77 frozen Validation
sessions. For each of the 1,531 Dolt/raw candidate-days, it obtains the
exact 126-session as-of-T history window and checks source/basis equality.
It reuses the existing issuer query, which restricts issuer evidence by
`available_on <= T` and dispute annotations by `known_on <= T`, then
cross-tabulates those observational classifications against accepted
T-day price status. The construction database, accepted price database,
candidate file set, RI semantic hash and auditor sources are bound in
[aggregate evidence](../evidence/box-candidate-prefix-issuer-at-t-2026-10-15.json).
No security ID, CIK, symbol, price or task-level mapping is published.

| T-day accepted price status | No known conflict observed | Contemporaneous issuer alias | Known identity conflict | Total |
| --- | ---: | ---: | ---: | ---: |
| Accepted T-day row missing | 876 | 77 | 29 | 982 |
| Exact accepted T-day match | 535 | 14 | 0 | 549 |
| **Total** | **1,411** | **91** | **29** | **1,531** |

The 106 observed-risk cases among the 982 consist of 77 same-CIK
contemporaneous aliases and 29 known identity/name conflicts. The 14
alias-risk cases among the 549 accepted-price matches show that accepted
price inclusion alone is **not** an official issuer certificate. Conversely,
the 876 observationally no-known-conflict cases may still have unknown
issuer, class, action or raw-price problems. The previous
[accepted-scope diagnosis](box-candidate-accepted-scope-2026-10-15.md)
remains true: all 982 were rejected by the older PIT full-closure research
identity gate. Its evidence can include information that arrived after T;
that retrospective result is not substituted for this T-dated observation.

This covers only the sealed 2024-09-30–2025-01-21 Validation prefix, not all
235 Validation sessions or any Train legacy-source candidate. The issuer
query provides an observational cross-check, not vendor/legal identity,
complete action/factor handling, accepted execution-period prices or
portfolio readiness. The auditor did not use future outcomes, Test/Fresh,
human labels, orders, returns or a box LEAN backtest.

Focused issuer/T-day bridge tests: **5 passed**, including a future-dated
issuer-link exclusion test. The actual local read-only audit generated the
linked evidence. Full project regression ran with
`STOCK_RADAR_TEST_LEAN=1`, including Native LEAN fixture tests.

**Regression: 814 passed, 8 skipped, 1 existing `websockets.legacy`
deprecation warning.** No box portfolio backtest ran.

The immutable background Train/Validation candidate workers were not
modified or stopped. Formal LEAN remains blocked by the independent issuer,
same-source execution price/action/factor, full signal and portfolio gates.

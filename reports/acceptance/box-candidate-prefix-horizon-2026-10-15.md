# Box candidate Validation-prefix accepted horizon metadata — 2026-10-15

**Result: all 549 candidates with an exact accepted T-day match have
matching-source accepted raw *metadata* records on each of the next ten
in-split trading sessions (5,490/5,490 dated records).** This is a data
coverage diagnostic, not a ten-day holding rule or execution-price
certification. The other 982 Dolt/raw candidates in the sealed Validation
prefix still lack an accepted T-day record and are outside this 549-case
subset.

The read-only `box-candidate-prefix-horizon-metadata-v1` auditor reruns the
hash-bound [T-day full-prefix audit](box-candidate-prefix-tday-2026-10-15.md)
over all 580 immutable candidate chunks for 2024-09-30–2025-01-21. It
checks that the accepted database and private candidate file hashes have
not drifted, reselects the exact T-day matches, and obtains the next ten
frozen exchange sessions without crossing the Validation split end. On
later dates it selects only `symbol`, `provider`, `feed` and `adjustment`
from the accepted database. It does **not** read post-T OHLCV values or
future outcomes. Aggregate hashes and counts are in
[the evidence](../evidence/box-candidate-prefix-horizon-2026-10-15.json).

| Measure | Observed |
| --- | ---: |
| Sealed Validation sessions | 77/235 |
| Dolt/raw candidate-days in prefix | 1,531 |
| Exact accepted T-day matches selected | 549 |
| Ten-session records expected | 5,490 |
| Matching raw-provenance records | 5,490 |
| Tasks with all ten records | 549 |
| Split-censored or missing records | 0 |

The 549 were selected by T-day accepted-price equality alone. No official
issuer certification or complete execution-horizon/action/factor gate was
applied. The availability of a dated record does not prove that its price,
split factor, dividend, delisting treatment or tradability is correct.
The 982 missing T-day cases cannot be promoted by this result. Train's
legacy split-adjusted source is still a separate, unbridged stratum.

Focused tests: **7 passed**, including a split-boundary check and a fixture
that proves later metadata queries need no OHLCV columns. A real local
read-only audit produced the linked evidence. Full-project regression with
`STOCK_RADAR_TEST_LEAN=1` included Native LEAN fixture tests.

**Regression: 812 passed, 8 skipped, 1 existing `websockets.legacy`
deprecation warning.** No box portfolio backtest ran.

No Test/Fresh rows, human labels, orders, returns or box LEAN backtest were
used. The immutable background scans continue. Official historical issuer
identity, accepted execution-period price values, corporate actions/factors,
complete signals and frozen portfolio rules remain open.

# Box RangeDetector Stage B — local diagnostic checkpoint

**Status: engineering ready; structure-quality exit pending.** This worktree
stacks on unmerged PR #25 → #24 → #21; the revised route is PR #23. It does not
authorize main merge or Stage C on the strength of detector-only observations.

## Pre-frozen independent audit

Before running either detector on the new set, `stage_b.freeze_blind_pool` wrote
an immutable private selection. SHA-256:
`f64acf27893960ed3ac449d398a89bf0cdf4396d170c6669e8ab5043644f15a5`.
File modification order also places selection before private detector audit.
The rule is a deterministic hash-priority draw from frozen RI v1's supported,
ready 126-session Train/Validation index, one security ID per task, 12 each for
2022/2023/2024/2025. The six familiar symbols, the previous 30-task pilot IDs
and Stage A's 96 diagnostic IDs were excluded before the draw. No detector
verdict, human label or future outcome affected selection.

48 distinct security IDs were selected: 31 Train, 17 Validation; 46 confirmed
and 2 probable membership. Eligible indexed security-day denominators by year
were 680,566 / 830,719 / 854,897 / 665,376. These are **indexed eligible
security-days, not all US issuers**. The query examines a capped hash-priority
candidate stream. A read-only check against the exact construction database
recorded by RI v1 (file SHA-256 matched) found one CIK with evidence already
available by each T for all 48. These 48 CIKs are distinct and none overlap the
prior pilot, Stage A diagnostic or six references. **This is still provisional**:
all 48 are observational `OBS` identities, zero are marked `official_identity`,
and two have incompatible-name flags. Cross-ticker issuer separation is not
certified until those conflicts and identity provenance are reviewed. This
batch cannot yet support a market-wide recall estimate or a passed issuer-level
independence gate. See the aggregate [receipt](../evidence/box-range-stage-b-2026-10-13.json).

## Actual data and six supplied unverified examples

Alpaca `feed=sip`, `timeframe=1Day` was queried anew on 2026-10-13 for all six
specified intervals. The bar counts, low/high extremes and old-band close
counts matched the supplied reference note: IREN 97/86, RIOT 95/88, APLD
106/101, SOFI 112/111, IONQ 52/51, POET 4 bars. The old bands remain scanner
statistics, **not** verified box boundaries or human positives.

RI v1 found an eligible, safe 126-session decision window at each of the first
five cutoffs. All five index entries use `legacy:alpaca:sip`, `split` basis; four
have confirmed historical membership, IONQ has probable membership. The exact
supplied intervals contained one source and one basis, zero known-split bars,
zero unsafe bars, and their RI bar count, extremes and old-band close counts
matched Alpaca SIP. This is interval reconciliation, not a claim that all older
history has identical raw/adjusted basis or fully resolved corporate actions.

| Candidate at specified T | Quantile zone T state | Confirmed pivot T state |
| --- | --- | --- |
| IREN | CONFIRMED | UNCERTAIN |
| RIOT | CONFIRMED | CONFIRMED |
| APLD | CONFIRMED | UNCERTAIN; older historical structure found |
| SOFI | CONFIRMED | CONFIRMED |
| IONQ | BREAKDOWN; older historical structure found | UNCERTAIN |
| POET | UNCERTAIN; older historical structure found | DEVELOPING |

POET's 2026-10-12 T is **outside frozen RI v1**, which ends before that date.
Its 126-bar diagnosis used a separate private Alpaca SIP daily prefix, not
Research Infrastructure v1 and not a research-grade quality verdict. The four
days from 2026-10-07 to 2026-10-12 were used only to inspect state at T; no
four-day box was inferred. POET's older source/basis, historical issuer identity
and action chain are unresolved. It is not a negative Ground Truth label.

## Blind detector output and human workflow

On the 48 pre-frozen tasks, T states disagreed for **33/48**. Quantile output:
14 CONFIRMED, 14 DEVELOPING, 3 BREAKDOWN, 16 NONE, 1 UNCERTAIN. Delayed-pivot
output: 2 CONFIRMED, 6 DEVELOPING, 1 BREAKDOWN, 24 NONE, 15 UNCERTAIN. No
correctness, precision, miss rate or alpha can be derived from those counts.
No threshold was tuned after seeing them.

An isolated private 48-task batch reuses the existing 42D / 52W / 48M renderer
and Label Studio v1.1 ontology at
`http://localhost:8125/box-label/v1.1/human/`. 48/48 daily views are full;
35/48 weekly and 2/48 monthly views reach their target lengths. Shorter views
display actual observed coverage. Private manifest hash:
`53c7ebfe442b5c33ada7d49d8ad7273a206cee39890920c65572af705b3de8d7`.
The existing 30-task pilot manifest remains at its prior hash
`a48d701967e765846233af4a8987ccde28b2842c77a8eada942a2725c6e8425d`.

Bundle verification checked every raw/window/tensor/chart hash, T cutoff,
split and unique security ID. In the authenticated browser, 10 distinct tasks
displayed all three charts without symbol/date/score. The isolated smoke path
saved one task, restored it after refresh, and created revision 2. The separate
**human** annotation database has not been created; formal human labels = 0.
An initial unused private task build failed the existing verifier because its
manifest omitted `stratum`. The corrected v2 batch passed. Automatic approval
review rejected deleting that unused local build, so it remains ignored under
the private data root and is **not** the live labeling batch.

## Tests and next gate

Targeted Stage A/B tests: **28 passed**. Full project pytest with
`STOCK_RADAR_TEST_LEAN=1`: **760 passed, 8 skipped, 1 existing websockets
deprecation warning** in 102.24 seconds. Native LEAN opt-in tests were enabled;
this did **not** run a Stage B strategy backtest. No future outcome, Test/Fresh
optimization, ML training or QC Cloud job was performed.

Stage B can exit only after the owner makes genuine blind structure judgments,
issuer aliases are checked, and a version-frozen comparison reports false
positives, misses, state mistakes, boundary differences and uncertainty with
denominators. The assistant must not fill those labels. Stage C lower-band
rules and outcome/LEAN work remain behind that gate. All detailed histories,
charts, private ID/date maps and labels are ignored local data and are absent
from this report and Git.

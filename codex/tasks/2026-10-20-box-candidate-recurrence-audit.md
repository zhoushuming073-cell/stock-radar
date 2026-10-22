# Box candidate recurrence audit — 2026-10-20

Continue the sealed Stage D candidate research with a bounded, read-only check of repeated candidate days for the same observed security ID inside each frozen split.

1. Reverify every accepted Train and Validation candidate chunk and use their complete dated folders as the frozen session calendar within each split.
2. Count episodes separated by more than 20, 60 or 126 observed split sessions. Publish only aggregate episode counts, repeated-day shares and largest episode size. Never export security IDs or their dates.
3. Keep Train and Validation separate. The missing month between splits and earlier warmup history prevent a claim that these episodes are independent 126-bar input windows or certified issuers.
4. Add boundary and tamper tests, run on real local receipts, update ACTIVE and the canonical ledger. Do not read future outcomes, Test/Fresh, labels or LEAN results; do not change formal data gates.

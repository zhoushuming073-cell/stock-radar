# Box issuer-alias as-of-T follow-up — 2026-10-14

**Result: five observed identity risks isolated; official provenance remains
unverified.** This read-only audit extends the Stage B/Stage C receipts. It
does not rewrite the frozen 48-task selection, construction database, human
annotations or historical acceptances.

The earlier audit established that the 48 selected IDs have distinct CIKs
*within the sample*. It did not ask whether each selected CIK also belongs to
another active security ID on its decision date. The new SQL joins only issuer
evidence available by T, the ticker episode covering the selected 126-session
window, and contemporaneously active other IDs. It verifies the recorded
construction database SHA-256 before opening it. The report exposes aggregate
counts only; the private row/CIK map remains outside Git with SHA-256
`879bdaffa6ad9f4fcc5a85bd57cb5697a839c7969de6dc7c9b76b94bb36bf422`.

| Classification | Historical sample rows |
| --- | ---: |
| One observed CIK/window episode and no known conflict | 43 |
| Same CIK also linked to another active security ID at T | 4 |
| Incompatible name evidence available by T | 1 |

Three of the alias rows have one other active ID and one has two. The
conflict/alias cases are quarantined for any later sample-level exploratory
analysis; they are **not** repaired by silently merging security IDs. The
43 remaining rows are observational with no *known* conflict, not official
issuer certificates. A current SEC CIK mapping or retrospective full-window
A/B/C flag would not by itself prove historical class-level continuity.

An in-memory regression fixture confirms that an older non-covering episode's
CIK, a later CIK observation, and a formerly active other ID cannot change the
T result. Focused issuer-audit tests: **2 passed**. No future outcomes, human
labels, LEAN/QC run, market data mutation, or Test/Fresh optimization occurred.
Full repository pytest with `STOCK_RADAR_TEST_LEAN=1`: **771 passed, 8 skipped,
1 existing `websockets.legacy` deprecation warning** in 97.92s. This exercised
the existing Native LEAN regression, not a new box-strategy backtest.
The [aggregate evidence](../evidence/box-range-issuer-alias-asof-t-2026-10-14.json)
is the public receipt. Formal historical identity and execution economics
remain open gates; only explicitly provisional engineering can continue.

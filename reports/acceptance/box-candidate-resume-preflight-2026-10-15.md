# Box candidate resume preflight — 2026-10-15

**Result: the new resume entrypoint checks existing candidate receipts before
allowing the unchanged writer to create missing chunks.** It is an operational
integrity guard, not a change to candidate selection or detector semantics.

## Finding and change

The existing candidate scanner checks expected chunk files during normal
writing. Its `--verify-only` path additionally rejects unexpected JSON files
and `.partial` files in each selected day folder. A resumed normal writer
could otherwise proceed without noticing those extra artifacts. The new
`scripts/resume_box_candidate_backfill.py` invokes `execute(...,
verify_only=True)` over the requested interval and calls the existing writer
only if the preflight succeeds and chunks are missing. If all chunks are
already present, it returns `already_complete=true` without starting a writer.
An exception in preflight prevents the writer call.

The scanner and every code-bound dependency used by the running Train and
Validation jobs are unchanged. The existing jobs continue; operators must
confirm a writer is stopped before using this wrapper to resume its split.
This preflight does not make concurrent writers safe.

## Real local acceptance

- Train 2024-07-01 from the frozen local Research Infrastructure v1 was
  checked through the new entrypoint. It verified **5/5 existing chunks**,
  **3,944 eligible security-days**, and **96 near-lower contexts**.
- The result reported `complete=true`, `missing_chunks=0`,
  `already_complete=true`, `run=null`, and `new_chunks=0`.
- Its verified file-set SHA-256 was
  `407252c54b700c2dfb35646b95c795beb5ad10541ae3ceff1edb774e3376fed5`.
- Focused tests for the resume wrapper and the existing candidate/full-state
  scanners: **12 passed**. The wrapper tests cover successful preflight then
  writing, preflight failure blocking writing, and a complete preflight
  skipping writing.
- Full project regression with `STOCK_RADAR_TEST_LEAN=1`: **800 passed, 8
  skipped, 1 existing `websockets.legacy` deprecation warning**. Native LEAN
  fixture tests were enabled; this did not run a box portfolio backtest.

No private candidate rows, market bars, issuer mappings, or credentials are
included in this report. Train and Validation background scans remain
incomplete. Their candidate contexts are engineering receipts, not verified
structure truth, official identity, executable prices, or returns.

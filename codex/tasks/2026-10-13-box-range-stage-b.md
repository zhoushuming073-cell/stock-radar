# Box RangeDetector Stage B — diagnostic and independent quality

> Owner authorization: 2026-10-13, “允许 之后都允许 不要再问”. This authorizes
> advancing the existing roadmap without repeated permission questions. It does
> not turn missing human labels or failed data gates into a pass.

## Scope

1. Preserve PR #21 → #24 → #25 as review dependencies; build Stage B separately.
2. Freeze detector code/config and a deterministic Train/Validation blind audit
   selection before examining detector outputs. Exclude the six familiar symbols,
   the old 30-task pool, and Stage A diagnostic security IDs. Do not use outcomes.
3. Reconcile the six supplied Alpaca SIP examples to dated RI v1 identity,
   source, basis, membership and data safety. POET's October decision is outside
   the frozen RI v1 horizon and must be explicitly non-RI if inspected.
4. Reuse the authenticated v1.1 Label Studio extension for blind daily/weekly/
   monthly human review, with a separate data root and smoke/human SQLite files.
5. Test isolation, causal boundary, immutable receipts, browser workflow and full
   regression. Keep raw bars, charts, identities and labels outside Git.

## Exit gate

Human structure review must precede any precision, miss or boundary-quality
claim. Resolve cross-ticker issuer alias separation for the blind pool. Report
all denominators and ambiguity. Stage C lower-band rules, future outcomes,
LEAN/QC and Test/Fresh evaluation wait for this evidence; no assistant labels.

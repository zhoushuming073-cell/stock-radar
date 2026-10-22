# Box Stage D candidate as-of-T issuer follow-up

The prior as-of-T issuer audit covered the frozen 48-task labeling pool. Apply
its same dated construction-source checks to all near-lower candidates from
the two complete Train/Validation days, without treating the construction
database as an official historical security master.

1. Reverify the private candidate receipts and frozen RI construction source
   hashes. Derive each candidate's 126-session window from the T-only RI
   provider and reject source/basis drift.
2. Reuse the existing as-of-T issuer-evidence, ticker-episode and review-
   annotation joins. Preserve known conflicts and contemporaneous active
   same-CIK aliases separately from observational no-known-conflict rows.
3. Store private identity/CIK/window mappings only in ignored local `data`;
   publish aggregate counts. Cross-tab with the prior raw metadata diagnostic
   in memory without printing security IDs.
4. Test provenance rejection and full project regression. Do not claim that
   observational rows have official issuer certification or LEAN readiness.

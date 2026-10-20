# Box Stage D post-scan distribution audit — 2026-10-20

Owner direction: continue the existing research path after the complete Train/Validation candidate scan. This bounded task improves candidate-domain evidence without changing detector, Research Infrastructure v1, or execution architecture.

1. Reopen the sealed Train and Validation candidate files and verify each complete file-set hash against the accepted full-split receipts.
2. Reject duplicate `(decision_date, security_id)` candidate keys, malformed dates or missing identities; report only aggregate counts by split, year and source/basis, plus concentration of candidate-days among observed security IDs.
3. Keep all identity/date mappings private. Publish only aggregate evidence and explicit selection-bias limits. No outcome, Test/Fresh, human label, signal or LEAN access.
4. Run focused tests and the read-only audit on actual local data. Update the canonical ledger and ACTIVE status; preserve the formal data gates.

This task does not define a new Stage E or authorize portfolio evaluation.

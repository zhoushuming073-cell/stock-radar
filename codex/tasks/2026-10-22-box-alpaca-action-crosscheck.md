# Box Alpaca corporate-action crosscheck — 2026-10-22

Continue the owner's free-source route for the bounded 142-day Validation
cohort. Query the existing connected Alpaca corporate-action endpoint for
the 28 observed symbols over the covered 2025 interval. Store the raw response
only in ignored local data. Compare any returned cash-dividend event against
the pinned Dolt dividend scan by exact symbol, ex-date and amount, including
the two earlier exposed review leads. Publish aggregate counts and hashes;
reject missing/mismatched source rows.

The endpoint response is not a certificate of complete history, even if
every returned record matches. Do not infer entitlement, portfolio cash,
returns or formal LEAN readiness. Run focused and full regression; update
the canonical ledger, ACTIVE and draft PR #28 with actual evidence.

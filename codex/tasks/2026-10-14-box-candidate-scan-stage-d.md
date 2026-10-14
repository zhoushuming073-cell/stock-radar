# Box Stage D candidate-only scan — bounded follow-up

The owner removed mandatory human blind review. This work follows the active
Stage D necessary-gate audit without claiming structure accuracy, returns or
execution readiness.

1. Keep the complete two-detector daily scanner intact as the full-state
   reference. Add a separate, resumable Train/Validation path that applies the
   T-only necessary gate and runs both detectors for every *possible* target
   row, including uncertain prefixes. Persist only `NEAR_LOWER_STABILIZING`
   contexts in private immutable receipts.
2. Bind receipts to the eligible population, candidate selection, gate,
   configuration, RI semantics, implementation and runtime versions. Reuse
   existing chunks only after hash/provenance and count verification. Keep
   security/date mappings and OHLCV out of Git.
3. On the complete 2024-07-01 Train reference day, require exact near-lower
   context equality, not only matching counts. Benchmark a separate Validation
   day and report both observed candidate proportions and compute times.
4. Test causal selection, unknown retention, duplicate/missing identity
   rejection, near-only storage and receipt integrity. Run full project pytest
   with Native LEAN opt-in; do not run a box portfolio backtest.

The next step depends on measured cost and remaining identity/raw-price
gates. Neither a bounded scan nor candidate retrieval is a formal signal
stream. Historical Test/Fresh and future outcomes remain closed.

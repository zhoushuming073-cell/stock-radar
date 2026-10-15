# Box candidate source-stratified data gates — 2026-10-15

**Result: existing identity and raw-metadata receipts now have a separate,
hash-bound source/basis intersection.** Across four previously audited,
nonrandom Train/Validation days, the execution-data gap is concentrated in
legacy split-adjusted candidates. This is a diagnostic of those four days,
not a population estimate or a formal LEAN acceptance.

The new read-only `box-candidate-source-gates-v1` tool reuses the existing
issuer/raw intersection and candidate-request parsing. It verifies the SHA-256
of both private gate receipts, requires their exact task-ID set to match,
recomputes the ordered candidate chunk-file-set hash, rejects partial files,
and only then joins each task to its source and basis. It reads no future
OHLCV values or outcomes. The original scanners and prior gate receipts were
not modified. [Public aggregate evidence](../evidence/box-candidate-source-gates-2026-10-15.json)
records source hashes and receipt hashes; security IDs, issuer mappings and
price rows stay in ignored local storage.

| Four audited days, by source/basis | Candidates | Known alias/name risk | Complete same-source raw metadata | No known conflict **and** complete raw metadata |
| --- | ---: | ---: | ---: | ---: |
| Legacy split-adjusted | 719 | 59 | 0 | 0 |
| Dolt raw | 61 | 8 | 59 | 51 |
| Total | 780 | 67 | 59 | 51 |

The 10-session horizon is a coverage probe and is not a holding-period rule.
The 51 observationally conflict-free Dolt rows are **not officially
identified or LEAN-ready**: raw-price economics, actions/factors, delisting,
benchmark, complete historical signal stream and frozen portfolio rules
remain independent gates. The 719 legacy split rows cannot silently inherit
the Dolt raw coverage, even if the ticker looks similar. Four selected days
cannot establish these rates across the unfinished Train/Validation scans.

The source/gate tool's focused tests, together with existing overlap, issuer
and metadata tests, passed **8/8**. Tests include file-set tampering, partial
files and mismatched candidate task sets. Full project regression with Native
LEAN opt-in: **803 passed, 8 skipped, 1 existing `websockets.legacy`
deprecation warning**. No box backtest, human
label substitution, Test/Fresh inspection or future outcome analysis occurred.

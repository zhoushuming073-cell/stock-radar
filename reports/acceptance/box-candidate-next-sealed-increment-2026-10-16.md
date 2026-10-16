# Box candidate next sealed increment — 2026-10-16

**Result: independent read-only verification extends the adjoining Train scan to 460/753 frozen sessions and Validation to 193/235.** The unchanged source/basis auditor checked only newly sealed sessions after the previous 453/189 checkpoint: Train 2023-06-22–2023-06-30 (7 sessions) and Validation 2025-07-03–2025-07-09 (4 sessions). The still-active writers' current day folders were excluded.

| New sealed segment | Train | Validation |
| --- | ---: | ---: |
| Sessions | 7 | 4 |
| Eligible security-days | 23,120 | 15,671 |
| Verified chunks | 48 | 35 |
| Near-lower contexts | 808 | 525 |
| Legacy Alpaca SIP / split contexts | 808 | 464 |
| Dolt / raw contexts | 0 | 61 |

Adding these nonoverlapping, consecutive segments to the previous verified checkpoint gives **460/753 Train sessions (2,122 chunks; 45,653 contexts)** and **193/235 Validation sessions (1,424 chunks; 27,225 contexts)**. This is scan coverage only, not structure accuracy, a complete signal stream or formal LEAN readiness. No source series were stitched.

The same 61 Validation Dolt/raw candidate-days passed the existing separate T-day accepted-price, issuer-observation and ten-session same-source raw **metadata** audit. **21/61** have an exact accepted T-day price match; **40/61** lack one; **56/61** have a complete diagnostic raw-metadata horizon. Of the 21 exact price matches, two have a contemporaneous issuer alias and one a known identity conflict. A separate decision-dated mirror audit finds **40/61 Nasdaq-only recent compatible references and 21/61 with neither recent reference**; all 61 have an older compatible CIK mirror observation that fails the frozen 31-day freshness rule. The underlying CIK mirror cutoff was already documented in the historical database acceptance; this cross-check measures its effect on the newly sealed box candidates.

Across the now continuous 193-session Validation prefix, the five disjoint three-gate audits cover **3,345** Dolt/raw candidate-days, including **1,276** exact accepted T-day matches and **3,241** complete raw-metadata horizons. The three reference-support audits cover the same population: 1,607 both recent mirrors, 798 CIK-only, 588 Nasdaq-only and 352 neither. [Aggregate evidence](../evidence/box-candidate-next-sealed-increment-2026-10-16.json) holds the four new hash-bound auditor outputs and checks cumulative arithmetic; row-level security/date mappings and prices remain ignored local data. The candidate file-set SHA-256 for the new Validation interval agrees independently across its source, data-gate and reference audits.

Mirror availability is not official source publication or security-class certification. The accepted-price database uses a retrospective whole-closure gate and cannot be applied as a causal T-day selection rule. Metadata are not executable price values, corporate-action economics or adjustment factors; the ten sessions are only a coverage diagnostic. No future price values, outcomes, Test/Fresh, human labels, orders, returns or box LEAN portfolio backtest were read or run. Official identity, executable data, complete signals and frozen portfolio rules remain open.

The two real source verifications and two real Validation audits exited successfully. Focused source, data-gate and reference tests: **8 passed**. No code changed; latest full Native-inclusive project pytest remains **818 passed, 8 skipped, one existing warning**, and was not repeated for this aggregate-only checkpoint.

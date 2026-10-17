# Box candidate decision-dated reference support — 2026-10-15

**Result: 1,549/2,329 Dolt/raw candidate-days in the verified 120-session Validation prefix have both recent compatible CIK and Nasdaq *mirror observations* at decision close T; 780 have only recent compatible CIK observations.** This narrows the historical identity evidence gap but does **not** certify legal issuer, share class, ticker continuity, actions or LEAN readiness.

The new read-only `box-candidate-reference-support-v1` auditor first runs the unchanged candidate source/basis verifier over 2024-09-30–2025-03-24. It selects only Dolt/raw candidate-days, reconstructs each 126-session window through T using frozen Research Infrastructure v1, and rejects source/basis drift. It checks whether the construction database's `ticker_episode` spans that whole window. It then joins only `membership_evidence.available_on <= T` on the same security and episode, requiring compatible name and exchange and the construction database's frozen **31-calendar-day** reference freshness limit. The existing decision-dated issuer query independently classifies known conflicts and contemporaneous aliases.

The rule file's Windows CRLF checkout bytes differ from the original LF bytes recorded in the frozen historical construction manifest. The auditor normalizes line endings only, verifies the resulting SHA-256 equals the construction manifest's pinned rules SHA-256, and records both manifest and rule hashes. This is a byte-format reconciliation, not a changed freshness rule.

| As-of-T issuer observation | Both recent compatible mirrors | Recent compatible CIK only | Total |
| --- | ---: | ---: | ---: |
| No known conflict observed | 1,399 | 745 | 2,144 |
| Contemporaneous issuer alias | 125 | 15 | 140 |
| Known identity conflict | 25 | 20 | 45 |
| **Total** | **1,549** | **780** | **2,329** |

No candidate had a recent compatible Nasdaq mirror without recent compatible CIK in this population. No candidate lost a prior compatible observation solely because of the 31-day freshness rule; all 2,329 had one ticker episode spanning the observed 126-session window. The membership-reference join found zero **recent** name/exchange incompatibilities, but the independent issuer query still found the 185 alias/conflict candidate-days above. A dual-source match does not resolve those 185 cases, nor does the remaining 2,144 observationally no-known-conflict population become officially certified.

The [aggregate evidence](../evidence/box-candidate-reference-support-2026-10-15.json) binds the candidate file set, frozen construction database, original historical manifest, normalized frozen rules, RI semantics and auditor source hashes. No private security ID, CIK, ticker, price, decision date or task mapping is committed. No post-T OHLCV values, future outcomes, Test/Fresh data, human labels, orders, returns or box LEAN backtest were read or run.

The CIK/Nasdaq inputs are pinned historical **Git mirrors** of reference directories, with `available_on` based on mirror availability. They do not prove upstream announcement timing, independent complete US-market coverage, official share-class identity or terminal economics. CIK can identify an issuer while several securities or classes share it. Formal box execution still requires official historical issuer/class resolution, accepted same-source raw execution prices and corporate actions/factors, a full signal contract and frozen portfolio rules. Train's split-adjusted legacy series remains a separate unresolved source stratum; this audit covers only Validation Dolt/raw candidates.

Focused source-support and reused gate tests: **5 passed**. Full project regression with `STOCK_RADAR_TEST_LEAN=1` (Native LEAN fixture opt-in): **818 passed, 8 skipped, one existing `websockets.legacy` deprecation warning**. No box portfolio backtest ran.

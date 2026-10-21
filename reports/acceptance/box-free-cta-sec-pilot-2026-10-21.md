# Box free CTA + SEC candidate evidence pilot — 2026-10-21

**Result: a bounded free-source identity path is feasible for some later Validation candidates, but zero candidates were promoted to formal LEAN readiness.** The [aggregate machine receipt](../evidence/box-free-cta-sec-pilot-2026-10-21.json) binds three sealed candidate-day file hashes, the frozen Research Infrastructure semantic hash, CTA download hashes, the construction database hash and the accepted raw-price database hash. Private symbol/security/date/CIK mappings and SEC review notes remain in ignored `stock-radar/data/references/box-cta-symbol-v1/`.

| Validation date | Sealed candidates | CTA symbol present | Dolt/raw candidates | Dolt/raw CTA present | CTA + exact accepted T-day + complete ten-session raw metadata |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2025-05-05 | 76 | 19 | 5 | 2 | 0 |
| 2025-07-01 | 156 | 47 | 14 | 7 | 5 |
| 2025-09-08 | 137 | 33 | 6 | 1 | 0 |
| **Total** | **369** | **99** | **25** | **10** | **5** |

The [NYSE public CTA directory](https://ftp.nyse.com/cta_symbol_files/) supplied actual daily CSV snapshots. Exact-case matching matters: the 2025-05-05 file contains distinct `TPC` and `TpC` records, so uppercasing would silently merge instruments. All 99 matched pilot rows have CTA listing-market code `N` and instrument-type code `0`; these codes are preserved as source values and do not become a certified security-class decision. CTA files were posted after the trading close, so they are retrospective corroboration, never T-close signal input. Absence from this CTA file is not proof that a candidate was unlisted on another exchange. The public listing begins in 2025-05 and cannot cover the 2021–2024 Train period.

For the 25 Dolt/raw candidate-days, the audit reused the existing dated-issuer observation query, accepted-price T-day exact-OHLCV check, and split-bounded ten-session raw-availability query. The five strongest cases all fall on 2025-07-01. Their private observed CIKs were cross-checked against five SEC 2024 Form 10-K cover pages filed between 2025-02-10 and 2025-03-14; each page states a matching class, symbol and NYSE listing before T. The private review file has SHA-256 `44d1b41836ea1cad221b87118484aae73561a2258b305bcccb46be017a4a1651`. [SEC EDGAR](https://www.sec.gov/search-filings/edgar-application-programming-interfaces) supplies the filing chronology and source documents; current filer metadata alone was not used as historical class evidence.

**Limits:** the SEC documents were reviewed by URL/accession and filed date, but their raw bytes were not collected into the trust catalog. A cover page is a dated class observation, not a complete no-event certificate. The ten-session raw check confirms row availability/flags in the Shape database, not accepted execution-price equality on every day or split/dividend cash entitlement. The 2025-09-08 diagnostic horizon is censored by the frozen Validation end. No cross-source price substitution was made. All 369 cases remain in their existing research strata; the five follow-up cases are private investigation leads, not executable box signals. Official lifecycle/action/factor coverage, accepted execution prices, full historical population and frozen portfolio rules are still open. No future OHLCV values, outcomes, Test/Fresh data or returns were read.

The focused regression for the new fail-closed CTA parser and public-output privacy check passed **2/2**. Full project regression with `STOCK_RADAR_TEST_LEAN=1` passed **826**, skipped **8**, with one existing `websockets.legacy` deprecation warning. The independent local Native LEAN integration module was separately confirmed **5/5 passed**. These are software regressions; no box portfolio LEAN run occurred.

## Next free-source boundary

The pilot supports continuing source-dated SEC class/event research on a bounded cohort. It does not supply a free full-history security master or same-source accepted raw execution dataset for all candidates. Expand only with source-level, dated, hash-bound evidence; keep unresolved candidates isolated. Formal box LEAN remains **NOT_RUN** under the owner's free-data decision.

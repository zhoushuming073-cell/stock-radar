# Box Stage D post-scan distribution audit — 2026-10-20

**Result: the sealed full Train and Validation candidate files contain no duplicate `(decision_date, security_id)` keys.** A new read-only audit rehashed all 4,167 Train and 1,748 Validation chunks against the accepted full-split file-set hashes. It found 78,607 and 33,226 candidate security-days, respectively; counts match the prior complete scan. No raw OHLCV, future outcome, Test/Fresh row, label or order was read.

| Split | Observed candidate days by calendar year | Distinct observed security IDs | Top 10 ID candidate-days | Median / maximum days per ID |
| --- | --- | ---: | ---: | ---: |
| Train | 2022: 29,980; 2023: 28,571; 2024: 20,056 | 3,901 | 766 (0.97%) | 18 / 84 |
| Validation | 2024: 8,720; 2025: 24,506 | 3,397 | 501 (1.51%) | 8 / 62 |

Train's first 125 sessions have no candidate because the 126-session context window is not yet available. The source/basis audit shows Train contains 77,355 legacy Alpaca SIP/split candidate-days, 1,247 Dolt/raw and five legacy public-EOD/split. Validation contains 29,497 legacy Alpaca SIP/split and 3,729 Dolt/raw. Dolt/raw Train candidate-days occur only in 2024; this and the unequal year spans limit any cross-year or cross-split quality comparison. Observed security IDs are not certified issuer or share-class identities. Repeated candidate-days for one ID are not independent examples.

The [aggregate evidence](../evidence/box-candidate-distribution-2026-10-20.json) contains no private ID/date mapping. Focused duplicate, bad-date and hash-drift tests: **2 passed**. Full project pytest with the actual `STOCK_RADAR_TEST_LEAN=1` opt-in: **820 passed, 8 skipped, one existing websockets deprecation warning**. The separate first attempt used the wrong `RUN_NATIVE_LEAN_TESTS` variable and yielded 810 passed / 18 skipped; it is not the Native-inclusive result. This audit does not estimate candidate recall, detector accuracy, future lift or strategy returns. Formal box LEAN remains deferred under the existing free-data identity, corporate-action and execution-price gates.

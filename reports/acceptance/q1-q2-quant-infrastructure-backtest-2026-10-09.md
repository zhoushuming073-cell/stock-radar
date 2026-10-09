# Q1/Q2 Quant infrastructure and bounded Native LEAN acceptance — 2026-10-09

**Overall: PARTIAL_BLOCKED_LOCAL_EXECUTION. Draft PR [#13](https://github.com/zhoushuming073-cell/stock-radar/pull/13); not merged.**

Source engineering and Daily product acceptance pass. The full local strategy execution gate does not: blocked methods are explicitly NOT_RUN, not zero-return backtests. QC Cloud is BLOCKED/NOT_RUN because mandatory local gates have not all passed. No new Cloud project/backtest IDs exist. No Vision/Fusion training, Q3 optimization, Historical Test/Fresh evaluation, broker orders or paid resources.

## 1. Baseline, architecture and freeze

Synced clean main `9e99659933b6666904b17cc7d383c4ef55b41248` before work. Selective Q2 provenance: Draft #10 head `7bb27096fefa648f0074ea08ec67f787b10f3910`. #10 is not merged or closed. The current implementation source receipt is `515da7c23b71aa1892e8b0b44170560db9f78866`; later changes are UI/provenance/documentation fixes, not score tuning.

Q1 independent namespace preserves accepted fuzzy-shape-v1 outputs exactly: 50 actual frozen historical windows,60/126 sessions, plus Hypothesis properties. Original Vision module/config/labels and Strategy2 remain protected. Q2 v1.1 corrects log position, monotonic undercut penalty, confirmed rally/retracement, multi-window stability, partial-period observation dates and calendar behavior. No best-window selection or return-driven threshold changes. [Accepted specification](../../docs/Q1_Q2_QUANT_RESEARCH.md).

Initial receipt `64f765e4720bb3b5c85a48135feb6e37238e72c94b1a0cc51f3f033d494d42cb` predates all strategy returns. Fixture regression exposed an old QC source pin; fixed-horizon code was isolated and the original adapter bytes restored. Bounded parallel security computation was then parity-checked. Initial and intermediate receipts are retained privately. Final pre-strategy receipt `7a175ee6fe9b5815207e5d1a964213cf005a11b4cbd4b16e27856f3f46a96efd` binds corrected execution and unchanged scores/dates/costs. Selector kernel `4e5d9f15e7002977a74d67d1637c24a2da28c0cf11414696dece2090485962a8` remained unchanged throughout actual signal generation.

Actual full-day serial/parallel reproduction: 3,278 eligible security-days, 2,971 candidate records, identical values/order/private mappings/hash. Q2 Train was invoked in Native LEAN twice independently: signal/data hashes and daily/fill/trade/completion journal bytes and metrics matched exactly. The reproduction was not published as an extra Run.

Native engine commit `82810ea63d5542f05dc58f9d1db0557cf174d0ea`, independent `D:\QuantConnect-LEAN`; actual DLL/source identity stored in each private manifest. LEAN alone owns cash/positions/fills. Frozen signals contain no selector code. [Execution methodology](../../docs/Q1_Q2_LEAN_METHODOLOGY.md).

## 2. Actual daily-use product

URL: **http://127.0.0.1:4174/lab.html#scanner**. Existing API8765 is a backend, not a second website. CLI:

```powershell
.venv/Scripts/python.exe scripts/scan_quant_daily.py --method all --top 20
```

As of **2026-10-08**, **CURRENT**, current eligible assets **13,199**. Q1 Qualified **2,999**, Watch 5,378, Wait 110. Q2 Qualified **0**, Watch 6, Wait 213. Overlap **211**, including Watch/Wait; not both-Qualified and not a buy list. Default display20 per method; an empty Qualified list is not padded.

Current eligibility reuses existing Phase1 active/tradable US equity-like classes; not certified common stocks only and not historical membership. Bars are homogeneous causal prefixes. Weekend/holiday/completed-session resolution, stale snapshot handling and hashes are explicit. Data coverage/exclusions and score distributions appear in machine evidence. Q1 daily score mean/std **58.1404/12.1391**; Q2 mass at0 represents failed channels, not a calibrated probability. No future labels used.

Actual installed Chrome smoke: Q1/Q2/all filters,20→10 display, expandable structure, market-chart link, actual Run Daily Scanner button, disabled running state, silent worker completion and automatic table refresh. Job took about269.1s; unchanged inputs reproduced snapshot `ece16721fd8212b5921783084021a04c3cc8e08bc0578513d452040912c0ddac`. Zero browser errors. Successful Market ingestion now calls the same silent scanner with an independent failure status; `--skip-watchlist` is explicit opt-out. [User guide](../../docs/DAILY_QUANT_SCANNER.md).

## 3. Candidate quality and historical coverage

Eight real, blind126-session PNGs inspected with existing mplfinance renderer: Q1 high/medium, Q2 Watch/reject. Q1 top examples showed previous strength/pullback/stabilization; medium examples also exposed thin/wick-heavy data, so a fuzzy score alone does not certify liquidity. Q2 Watch examples often lacked confirmed stabilization; monotonic trends/declines were rejected. This is developer structural QA, not user labels, prediction accuracy or proof of active buying. Images/mappings stay private.

Continuous dates pre-registered before outcomes: Train2023-01-03–2023-02-15 with execution reserved through2023-03-02; Validation2024-09-30–2024-11-12 with execution through2024-11-26. **Bounded intervals, not a full Train/Validation census.** Only frozen supported confirmed/probable T membership is used; unknown excluded. Q2 requires safe homogeneous long history. No current-survivor fallback.

- train: 3,326 distinct supported IDs; 395 no longer observed as eligible at the frozen core end. This is not attested delisting or entitlement coverage.
- validation: 4,099 distinct supported IDs; 815 no longer observed as eligible at the frozen core end. This is not attested delisting or entitlement coverage.

The frozen database still has disappeared-price and unknown-population gaps, imperfect issuer continuity and uncertified full-market/action coverage. Same-T eligible background and censoring are reported, not advertised as unbiased US-market representation. Detailed status, score distributions, overlap and source-basis counts are in machine evidence. Source windows/index/database remain read-only.

## 4. Local portfolio results — exploratory only

Primary contract: Qualified Top10, T+1 open proxy, max10 positions, equal available cash across remaining slots, no overlapping same security, tenth holding-session close, no TP/SL optimization,10bps slippage and existing illustrative/unconfirmed fee profile. No alternatives selected after seeing returns. Annualized metrics in short pilots are fragile; CAGR is null below252 sessions. Dividends/unknown actions/terminal entitlements/auction microstructure are not certified.

| Split / method | Signal days / eligible security-days | Selected signals | Native status | Net return | Max drawdown | Trades | Fees | SPY |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| train / Q1 | 31 / 101,478 | 310 | NOT_RUN_DATA_BLOCKED | — | — | — | — | — |
| train / Q2 | 31 / 101,478 | 25 | PASS_EXPLORATORY_PROXY_ONLY | 1.3394% | -5.5185% | 14 | 2143.9729 | 4.4614% |
| validation / Q1 | 32 / 127,716 | 320 | NOT_RUN_DATA_BLOCKED | — | — | — | — | — |
| validation / Q2 | 32 / 127,716 | 59 | PASS_EXPLORATORY_PROXY_ONLY | -2.5963% | -7.7590% | 27 | 6327.2913 | 4.6866% |

- **train/q1:** {"missing_10session_fill_prices": 1, "unsafe_identity_or_fill_prices": 1}; missing required bars 10. Entire method blocked, no candidate substitutions. Detailed IDs stay private.
- **validation/q1:** {"missing_10session_fill_prices": 1}; missing required bars 6. Entire method blocked, no candidate substitutions. Detailed IDs stay private.

Passing results are visible in original **Backtest** and **Compare**. Real UI smoke verified Q2 Train41 curve points/14 trades and Validation42 points/27 trades, benchmarks, frozen read-only controls, explicit Shape/proxy domain and source hashes. Both actual portfolio and Compare views have zero browser errors. A CSS hidden/grid conflict and metadata fallback were repaired and retested. Native audits reconciled each daily cash amount to actual fills and verified all completed holds at ten sessions; maximum position count did not exceed10 (Train5, Validation10). Original Native JSON and journals stay private.

Gross cost addback is attributed at actual Native quantities, not a counterfactual cost-free portfolio. Complete Sharpe/Sortino, trade distribution, worst trade, turnover/fees, year and diagnostic regime breakdowns are in machine evidence. A blocked method has no portfolio curve, trade statistics or invented zero return.

## 5. Post-selection candidate diagnostics

Reuses existing Scanner label/metric implementation, independently after frozen signals. Primary +5% target touch over10 sessions from T+1 open; ten-session SID cooldown; raw Top5/10/20 ranks fixed, no refill. Same-T supported background. Unsafe/missing forward data and raw split-crossing horizons censored and counted. These are vendor-price proxy Y diagnostics, not Human Ground Truth and not inputs to Q1/Q2. Event suppression uses the whole Qualified stream; portfolio overlap is a separate execution rule.

| Split / method | Top10 labeled | Precision | Lift | Independent Top10 events | Event Precision | Event Lift | Mean MFE / MAE |
| --- | --- | --- | --- | --- | --- | --- | --- |
| train / Q1 | 305 | 60.9836% | 1.1618 | 38 | 68.4211% | 1.3035 | 8.9725% / -5.6252% |
| train / Q2 | 25 | 68.0000% | 1.2955 | 14 | 71.4286% | 1.3608 | 8.6119% / -4.0563% |
| validation / Q1 | 319 | 57.0533% | 1.1053 | 33 | 39.3939% | 0.7632 | 9.8774% / -7.3557% |
| validation / Q2 | 59 | 69.4915% | 1.3462 | 28 | 60.7143% | 1.1762 | 9.0313% / -5.6534% |

Primary diagnostics are not portfolio win rate. Pooled vs event counts differ materially, especially with recurring Q1 candidates. Regime slices use SPY vs causal200-session MA; no regime filtering of the selector. Full censoring counts, Top5/20 and year/regime slices remain in machine evidence. Selection bias and incomplete disappeared outcomes remain; none of these numbers prove alpha.

## 6. Regression, immutable artifacts and limitations

Final full pytest: **756 passed, 0 failures, 0 errors, 0 skipped**. `STOCK_RADAR_TEST_LEAN=1`; actual Native fixtures include ordinary and early13:00 tenth-session closes. One existing `websockets.legacy` deprecation warning. Actual native strategies are reported per gate above, never inferred from fixture passes.

First regression caught six old QC frozen-source failures; these were fixed by isolation/restoration, not updating old pins. A Windows virtualenv pythonw worker startup issue was resolved with the base pythonw executable; serial/parallel synthetic and full real-day parity pass. The original serial generator correctly rejected its old receipt before Validation after engineering corrections; final receipt resumed the unchanged study. Historical acceptance reports were not rewritten.

**5,207 protected files checked; 0 changed**: original labels/images/receipts, Strategy2, Vision config/source, frozen Core and Fresh database. No private images, mapping rows, labels, credentials, raw OHLCV or LEAN checkout committed. Private browser screenshots, detailed gate IDs and Native artifacts remain ignored. Source/config/docs/tests and aggregate evidence only are public.

Native subscription logs can request files outside supplied possible holding windows; the actual required holding paths are preflighted, no fill-forward substitution is used, and per-day fills/cash/closed horizons reconcile. Formal raw PIT readiness remains unchanged/BLOCKED. Daily current data maintenance does not mutate the frozen historical research database.

## 7. QC Cloud and release gate

**Mode BLOCKED; strategy Cloud NOT_RUN. No new project/backtest IDs.** Required local Q1/Q2 gates have not all passed. No Cloud staging, raw local OHLCV upload or QC-reference export attempted; existing Terms/export hold remains. Old mapping/split Cloud smoke passes are not this task's Q1/Q2 validation. [Cloud boundary](../../docs/Q1_Q2_QC_CLOUD.md).

Local Daily watchlist is technically usable on this branch. Whole work order is not READY/PASS; PR13 remains Draft and main is not merged. Draft10 stays open until an accepted replacement merges. Next research decision: resolve the frozen Q1 execution/terminal-price dependencies with trusted source evidence under the unchanged study, then repeat the local gate. Do not drop hard candidates, tune for profit, start Vision/Fusion or bypass Cloud gates.

[Aggregate machine evidence](../evidence/q1-q2-quant-infrastructure-backtest-2026-10-09.json).

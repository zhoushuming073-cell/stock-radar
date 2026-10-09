# Q2 v1.2 — High-beta liquid channel

Version: `high-beta-liquid-channel-v1.2`. This is an independent Quant-only daily candidate selector. It does not replace frozen `parallel-channel-v1.1`, Q1 or their LEAN execution results. [Actual acceptance](../reports/acceptance/q2-v1.2-high-beta-channel-2026-10-09.md).

## Pipeline and defaults

1. Supported current common-stock classification and homogeneous Alpaca SIP OHLCV/benchmark evidence.
2. Market gates: SPY126 beta ≥2.0 and ADV20 ≥$50 million. Preferred tier requires both beta ≥2.5 and ADV20 ≥$100 million. A shape score cannot compensate for a failed gate.
3. Repeated, approximately parallel monthly/weekly range, independent boundary tests, completed swings and stable adjacent windows.
4. Daily low-support position and readiness. Watching and early reversal are different states; neither places an order.

Configuration is [high_beta_channel_v1_2.yaml](../config/high_beta_channel_v1_2.yaml). Defaults are shape priors registered before the first scan, not optimized parameters. No Y/forward returns, Test/Fresh efficacy or known-ticker approval rate was used to set them.

### Market features

Beta is intercept-inclusive paired OLS on aligned **daily simple returns**, stock against SPY. The last126/60 exchange-session returns require105/50 valid paired observations. QQQ126/60 are supplementary. Reindex before returns so a missing day cannot become a false one-day return. Absolute stock returns above50% or benchmark returns above20% are excluded and counted; an outlier in the mandatory SPY126 window quarantines admission. Benchmark variance must exceed1e-12. Missing mandatory SPY, inconsistent provider/feed/basis, nonpositive prices, incomplete decision bars and missing exchange sessions reject explicitly. Raw and joint-split evidence require the benchmark to use the same basis and provider.

ADV20/60 = mean(close × consolidated SIP volume), with price and volume adjusted jointly. This is a daily notional proxy, not exact intraday dollar turnover. Constant joint split scaling leaves amount and beta unchanged; vendor-adjusted data do not establish historical dated-identity or exchange-action certification. Historical use must supply separately certified evidence, and the current-listing adapter does not provide it. IEX data cannot be blended into this calculation. [Provider price/volume adjustment contract](https://docs.alpaca.markets/us/reference/stockbars).

Supplementary features: ATR20/60 relative to price, annualized realized volatility20/60, high/low range20/60, up/down-day amount ratio, recent amount relative to the prior106 sessions, and20/60-session excess performance relative to QQQ. These are OHLCV proxies for trading activity; they do not prove institutional inflows.

### Channel features

Reuse v1.1's causal confirmed pivots, robust log-price support/resistance fit, independent touch counting and T-clipped partial weekly/monthly buckets. Weekly windows:12/16/20/26 buckets; monthly:9/12/15/18. Require at least205 daily bars. Exact original fit tests remain in the private per-window diagnostic, including sufficient distinct touches, width, coverage and parallel error.

- Log width:0.12–1.0.
- Drift normalized to126 exchange sessions: log drift between log(0.90) and log(1.18). This rejects persistent falling/rising channels rather than rewarding low price alone.
- Completed full swings = alternating confirmed boundary pivots /2; minimum1.5. Fractional values expose the half-cycle count rather than inventing complete cycles.
- Clarity0–100:25% boundary retest quality,25% completed-swing quality,20% parallel quality,15% interior coverage,15% normalized-drift quality. Minimum62.
- Require a pair of adjacent eligible windows in at least one timeframe. Across all eligible windows, boundary spread≤35% of median log width, position spread≤20 percentage points and normalized log-drift spread≤0.12. A single favorable window cannot qualify alone. Not every stock has both valid monthly and weekly windows.
- Record lower/upper bounds, full swings, normalized drift, rejection quality, primary timeframe and all failed tests. These bounds describe this data's adjusted price units, not a broker limit price.

### Daily readiness

Position = log(close/lower) / log(upper/lower). 0–30% is preferred low support;30–45% is secondary watch; above45% is not a low-support candidate. Breakdown is separate: position below−8% or two successive closes materially below support. Slight undercuts retain an explicit risk flag and cannot receive the near-support bonus.

Early reversal requires **all**: recent low not materially below the preceding lows, two rising closes, average recent close placement≥55%, close above the five-day average, no continuing fast decline and no expanding red bodies. Decline flag includes consecutive falling closes, five-day return below−6% or repeated new lows. One green candle is insufficient. Last-day rise>8% or five-day rise>15% means extended/wait. Broad definitions are disclosed in the source and config; daily constants are versioned source semantics, not separate live sliders.

`structure_qualified`, `near_support`, `stabilization_pending`, `early_reversal`, `breakdown`, falling/extension/undercut risk flags are independent diagnostics. Ranking only includes nonrejected candidates: preferred market tier first, early reversal before waiting within the tier, then65% clarity+25% entry score+preferred-tier bonus, deterministic security-ID tie break. Display20/50 never relaxes gates or pads results.

## Use locally

```powershell
.\.venv\Scripts\python.exe -B scripts/scan_high_beta_channel.py --asof 2026-10-08 --workers 1 --verify-parallel
.\.venv\Scripts\python.exe -B scripts/diagnose_high_beta_channel.py
.\.venv\Scripts\python.exe -B scripts/prepare_high_beta_review.py
$env:STOCK_RADAR_TEST_LEAN='1'
.\.venv\Scripts\python.exe -m pytest -q
```

Outputs are private under `data/research/high-beta-channel-v1.2/`. Daily immutable filenames contain the complete snapshot hash; only this version's `latest.json` pointer moves. Existing Daily v1.1 snapshots, frozen historical databases, Q1/Q2 candidates, Native artifacts and Human/Vision labels are not overwritten. Diagnostics/review preparation reject changed current inputs or code instead of mixing them with a saved snapshot.

Once the local API has loaded the new source, open `http://127.0.0.1:4174/lab.html#scanner`, choose **Q2 v1.2 · High-beta liquid channel**, then Run or Refresh. A bounded subprocess runs silently; no console windows or broker actions. Existing API port8765 remains the normal backend. The baseline option continues to show Q1+Q2 v1.1.

**Acceptance environment limitation:** tool automatic approval rejected restarting the existing8765 process twice, including after explicit user authorization. The process was not terminated and remains on old code. The new endpoints/UI were verified with an actual temporary8776 backend and browser URL interception, not a mock. That temporary service was stopped after testing. Before normal use, restart the Stock Radar API yourself or reboot Windows and use the existing launcher; its new process will import the updated source. Check `/api/research/high-beta` returns this version. Merely refreshing4174 does not reload an already running Python API.

## Blind quality review

`http://127.0.0.1:4174/high-beta-review.html` after API reload. Twenty new symbols exclude all12 known diagnostic preferences, with admitted/boundary/random-other market-gated examples and a fixed seed. Each task shows the same anonymous Monthly/Weekly/Daily tripanel. It hides ticker, date, absolute price scale, score, machine status and outcome. The API validates image hashes and permits only anonymous IDs plus PNGs; private mapping never enters visible task JSON.

Judge repeated channel clarity, low-support location and readiness. Save & next, Previous/edit, Skip and refresh persistence are supported. Export your JSON after20 judgments; answers remain browser-local. Do not clear browser storage before export. This is shape QA, **not** Vision training Ground Truth. Ephemeral synthetic browser-test choices were cleared; zero formal judgments are asserted.

The sample is deliberately market-gated and partly boundary-enriched. It supports finding false positives, false negatives and restrictive rules within that sampled domain, not estimating whole-market sensitivity or alpha. A human conclusion is pending; developer rendering inspection is not the user's subjective label.

## Scope and release gates

Current broad pool contains other instruments; only supported unique common listings enter the market calculation. The classification directory can be up to7 calendar days old and requires exact normalized issuer description. It does not certify historical issuer continuity. Unsupported/unknown classifications are excluded, never silently promoted. This is not a complete historical or current common-stock census.

No trusted sector dataset is installed; production sector counts are explicitly Unknown. Manual post-selection company-source annotation in the report must not be mistaken for a complete machine sector taxonomy. No dividend-total-return market beta is claimed.

Keep the independent stacked PR Draft. Human blind review and production API reload are pending; sparse candidates may indicate excessive channel screening. Do not loosen defaults to get six known positives, claim a profitable strategy, launch new LEAN/Cloud efficacy runs, train models or merge main. A later independently authorized return study needs frozen v1.2 and matching identity/data/partition/cost/execution rules plus SPY/QQQ incremental and beta-exposure reporting.

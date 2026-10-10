# Q2 v1.2 — free QC Cloud exploratory study

## Current state

**CLOUD NOT_COMPLETED / ACCOUNT SUSPENDED AFTER ASSISTANT ERROR.** This guide's
free web-IDE steps below are historical preparation, not an instruction to
retry. After this guide was written, the assistant uploaded zlib/base64-encoded
modules executed via `exec`; QuantConnect flagged them under Terms 2.6 and
suspended the account. No valid Q2 Cloud backtest was produced. The user
directly instructed the assistant to stop QC attempts. Do not access or launch
the Cloud project again without fresh user authorization. The subsequent
[bounded local LEAN proxy report](../reports/acceptance/q2-v1.2-local-proxy-2026-10-10.md)
is separate and generated no trades.

**Prior checkpoint (superseded): SOURCE PACKAGE READY / CLOUD NOT_RUN.** The user directly authorized a separate
multi-year Q2 v1.2 exploratory study, then requested the agent click Backtest.
Two initial editor-bind calls timed out. At the user's request the agent reopened
project37482228 in the right panel and the DOM became readable. Its current
`main.py` is still **StockRadarDataValidation**, not Q2 v1.2. No source upload,
new build, new project or Backtest click occurred. The displayed build message
belongs to the previous project code, not this package.

QC Terms3.3(b)(x) restrict automatic access to officially provided interfaces;
the free route here is human web-IDE control. Do not use browser scripting or
hidden session endpoints to bypass this boundary. Initial Git fetch failed;
the retry succeeded and local/remote main both remain2db3f5c. The source branch
is pushed; main has not been merged.

This authorization does not release Q1's blocked experiment or merge Draft PR15.
It does not authorize paid resources, raw QC exports, parameter optimization,
model training, brokerage orders or a Fresh/OOS alpha claim.

## Fixed experiment

| Field | Value |
|---|---|
| Selector | `high-beta-liquid-channel-v1.2` |
| Experiment/domain | `q2-v1.2-qc-native-exploratory-r1` |
| Dates |2021-01-04 through2025-12-31; five complete calendar years |
| Initial capital |USD1,000,000 |
| Entry |Fixed T-close signal → next session09:30 minute Open observed09:31 |
| Selection |Qualified early reversals only; unchanged preferred-tier ranking; Top10 |
| Position limit |10; no overlapping same SID; equal remaining cash slots |
| Holding period |10 sessions including entry; native market-on-close exit |
| TP/SL/gap guard |None / none / disabled, matching registered parent execution |
| Participation |Existing2% ADV limit |
| Slippage |10bps each side |
| Fees |Frozen illustrative uSMART schedule; uniform across years, not verified historical tariffs |
| Ledger |Native LEAN cash, positions, orders, fills, corporate actions |
| Baseline |Native QC SPY benchmark; no completed beta-adjusted alpha analysis |

Dates/weights were fixed before this Cloud study returns. The historical range
overlaps previously inspected research dates; it is **not new untouched OOS**.
Formal blind Q2 human shape QA remains pending. Sparse/zero trades may reflect
the unchanged restrictive selector; do not relax it after seeing returns.

## Same selector, separate data transport

The generator extracts the original Settings/beta/market/channel/daily/rank
function ASTs and reusable robust channel helpers; it only relocates imports.
The original native fixed-horizon execution source is copied unchanged.
Stock Radar remains the strategy owner. QC hosts these generated Stock Radar
functions and separately consumes their fixed, private prior-session signals.
The execution policy contains no Q2 formula. This is the existing Cloud Mode A
boundary, not a second hand-coded implementation.

QC data is explicitly `quantconnect / qc_native / qc_cloud_exploratory`, not
Alpaca/SIP and not locally certified historical PIT. Historical Fundamental
objects, common classST00000001, non-DR status, known IPO date and native SID
define the Cloud pool. No current ticker list, name-only join or missing-universe
fallback. QC Fundamental coverage is a provider-specific subset; actual annual
coverage and disappeared-security participation remain unverified until Cloud.

Typed RAW history → split events effective≤T → joint price/volume adjustment.
Future events cannot change a past window. Missing sessions/outliers/unknown
identity/fractional adjusted volume retain original rejection gates. RAW
close×volume provides a split-invariant coarse liquidity gate; paired126-session
beta follows; full up-to430-session windows reach the original selector.
No market cap, TopK liquidity truncation or known-positive ticker substitution.

The Cloud transport fixes a MOC fee reference that is `None`: fees use native
security price and the unchanged fee formula. Constant slippage applies to MOC;
the custom Open fill replaces the default fill once with observed Open plus
10bps. Native dividends enter portfolio cash; inherited closed-trade annotations
exclude ordinary dividends, so summed trade P&L is not a full total-return ledger.
End logs disclose observed vs expected sessions and remaining holdings.

## Generate and check locally

```powershell
.\.venv\Scripts\python.exe scripts/prepare_q2_cloud_exploratory.py
.\.venv\Scripts\python.exe scripts/verify_q2_cloud_exploratory.py
$env:STOCK_RADAR_TEST_LEAN='1'
.\.venv\Scripts\python.exe -m pytest -q
```

Private output: `data/research/q2-v12-cloud-exploratory/`.
`upload-manifest.json` binds file bytes, frozen original configs, selector,
native policy and transport to SHA256 receipts. The ZIP contains only own Python
source; no bars, security/date mapping, labels, credentials or previous results.
10Python files plus default notebook fit free25-file/32KB quotas. Local full
regression:838 passed,0failures/errors/skips, one existing warning, actual Native
LEAN fixtures enabled. Twelve real local QA symbols /2,616 bars give exact
generated-vs-original mathematical equality; these are not Cloud universe tests.
Parent freeze and5,207 protected file hashes are unchanged.
The ZIP is a local transfer container; direct ZIP import into QC is not claimed.

## Free web IDE steps

Project37482228 contains earlier smoke validation history. Prefer a separate
Python project named **Stock Radar Q2 v1.2 Exploratory** so previous smoke code
and backtest evidence remain intact. We have not created that project.

1. Create the Python project in the QC website.
2. Open the local `upload` directory. Replace the new project's `main.py` with
   its complete generated content. In Explorer → New File, create each of the
   following nine files and paste its complete content, without Markdown fences:
   `sr_q2.py`, `sr_channel.py`, `sr_math.py`, `sr_contracts.py`, `sr_execution.py`,
   `sr_sessions.py`, `sr_config.py`, `sr_data.py`, `sr_fill.py`.
3. Ensure `main.py` defines `StockRadarQ2V12Cloud`; `sr_config.py` has version1.2,
   dates2021–2025 and the receipt matching the local manifest. Save all files.
4. Click the **Backtest** icon. A successful build alone is not a completed run.
   Keep the free node; do not select an upgrade or optimization. QC can continue
   a launched job while its IDE is closed.
5. Share the Backtest result URL and the normal Statistics screenshot plus the
   short `SRQ2C` aggregate log. If build/runtime fails, share that error.
   Do not download/export raw history, factor tables or signal/reference-price
   corpora. No Object Store or hidden session-cookie API is used by this package.

Source/file quota reference: [QC project files](https://www.quantconnect.com/docs/v2/cloud-platform/projects/files).
Launch reference: [QC backtesting](https://www.quantconnect.com/docs/v2/cloud-platform/backtesting/getting-started).
Data boundary: [QC terms](https://www.quantconnect.com/terms/).

## Acceptance after a real Cloud run

Record project/backtest ID, source receipt, actual engine/build when exposed,
Completed status, full expected calendar observation, yearly candidate funnel,
fees, trades, open holdings, native statistics, SPY comparison and runtime limits.
Inspect corporate-action and daily-close behavior. A runtime/data gate failure
is a failed study, not an invitation to narrow the universe or fabricate a
zero-return result. Free-node throughput for the full historical pool is pending.

Local AST parity, real local-bar equivalence and Native fixtures do **not** prove
QC Cloud history semantics or the complete multi-year execution. No Cloud return,
build success, official strategy acceptance or profitability is asserted yet.

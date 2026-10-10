# Q2 v1.3 relaxed channel plugin — local engineering acceptance

**Date:** 2026-10-10

**Branch:** `feature/q2-v13-relaxed-channel-plugin-20261010` from `main ccdf13f`

**Status:** plugin/package and local input gates PASS; **user's final Q2 portfolio backtest NOT_RUN**.

## Scope and frozen decisions

The independent plugin is `q2_relaxed_channel_v1_3@1.3.0`, method
`high-beta-liquid-channel-v1.3`. It uses a dated Research Infrastructure v1
historical security ID, up to 430 host-supplied past OHLCV sessions, and only
features available by signal day T close. The existing interface-v1 files and
QC validation source hashes remain byte-identical. The additive adapter is
`src/radar/lab/research_adapter.py`; existing imported plugins retain the old
context and data path.

The market gate remains SPY beta 126 >=2.0 and ADV20 >=USD 50m, with the
>=2.5/>=USD 100m tier used only in ranking. One eligible weekly 12/16/20/26
or monthly 9/12/15/18 fit qualifies. The configured minimum is one complete
swing, clarity 55, approximately -15% to +25% normalized 126-session drift,
basic width/contact/coverage/parallel checks, and log position <=55% of the
chosen channel. A position <=35% ranks better. At least one of four causal
readiness confirmations is required. A >8% last-session or >15% five-session
rise waits. Severe downside acceleration requires a five-session drop below
-12%, three falling closes, and average red body >=4% over the last three.
The rank formula is 50% structure clarity, 25% readiness count, 15% lower
position, 10% preferred market tier. Daily selection caps at 10.

The local LEAN host is the only execution engine for this backend. The default
resolved Q2 contract is T-close decision, next-session Open proxy, up to 10
new candidates/day, 30 simultaneous positions, maximum 10 holding sessions,
no configured take-profit/stop-loss, `equal_cash` sizing, 10 bps slippage and
fee profile `usmart_hk_us_pro_spec_sep2026_unconfirmed`. The actual Run records
these values. No execution threshold was tuned to returns.

## Data provenance and candidate-only funnel

The frozen core database SHA-256 is
`b2d11cabf686b473566fbc8623e6afd74fc55bb48baf3a85f9e43d43104e030a`;
Research Infrastructure v1 semantic hash is
`74b765911a8a4f18b2074cd8d9e529b25b54afade15309a148b0ca43340b80be`.
The source/config remained unchanged. Dated membership comes from
`shape_research_universe_v1`, not the current active ticker list. Stock
OHLCV/ADV uses homogeneous Alpaca SIP split-adjusted history; the operational
market database supplies only the separately tagged SPY/QQQ benchmarks.

The pre-registered bounded Validation window `2024-09-30` through
`2024-10-11` was evaluated **without forward labels, trades, equity or future
portfolio returns**:

| Stage | Security-days |
| --- | ---: |
| Eligible dated membership | 39,837 |
| Jointly sourced, market-input-safe | 33,718 |
| Beta and ADV market gate | 679 |
| At least one clear weekly or monthly channel | 110 |
| Lower 55% region | 74 |
| Readiness and final selection | 55 |

There were 10 signal sessions, with 5–8 selections per session. These are
security-days, not 55 independent stocks or trades. Exclusions included
6,119 unsafe market inputs, 28 unavailable/unsafe histories after the market
gate, 541 without a clear channel, 36 above the low region and 19 missing
readiness. The dated pool includes 5,677 member-days from the Dolt source;
these are not promoted to the SIP split-adjusted dollar-volume market gate.
The private per-date candidate audit remains in ignored local data at
`data/strategy-lab/q2-v13-candidate-funnel.json`.

## Local acceptance

- ZIP loader and actual `RunManager.import_zip` path accepted the exact
  five-file archive. The ZIP remains local in `data/exports/` for the user's
  own import; no live Q2 Run was queued.
- Real dated history is T-clipped, returned as a defensive copy, and missing
  or future history is refused. A later-ended historical security ID remains
  addressable. Mutating the current-snapshot provider cannot change RI v1
  provenance. Synthetic post-T mutation did not change the plugin's T output.
- Repeating the real `2024-10-01` selection produced identical rows and ranks;
  both non-empty and empty candidate cases passed.
- One real bounded `2024-10-01` signal input was frozen for LEAN: five Q2
  signals, 66 execution-price rows, source/manifest hashes, engine identity and
  execution settings were verified. **LEAN was not invoked for this Q2 Run.**
- A separate six-day synthetic Native LEAN golden fixture ran successfully:
  **2 passed, 3 deselected**. This checks the installed local engine and host
  execution bridge; it is not a Q2 portfolio result.
- Full project regression after the additive refactor: **724 passed, 10
  skipped, 1 third-party deprecation warning** in 100.57 seconds. The frozen
  QC source-hash validation tests are included and passed. `node --check`
  passed for the Lab JavaScript.
- The Stock Radar 8765 scheduled API was restarted; its health endpoint and
  RI v1 semantic receipt responded, and the existing 4174 Lab page served the
  Research Infrastructure v1 option. No second site was created.

## Interpretation limits and next action

Research Infrastructure v1 reduces but does not eliminate historical survivor
bias; unknown identities and some later-disappeared sessions remain uncovered.
Early Train beta observations can be excluded because SPY benchmark history
does not extend before the operational SIP series. LEAN receives daily
split-adjusted Open/Close proxies, not intraday order-book or path data, and
termination wealth is not fully PIT-complete. A reused historical ticker with
multiple security IDs in one Run is rejected rather than silently combined.

The user will import `q2_v13_relaxed_channel_plugin.zip` at
`http://127.0.0.1:4174/lab.html#lab`, select Q2 v1.3 and a research split,
confirm the displayed backend/execution settings, then start the one final
local LEAN portfolio backtest. The resulting gain or loss must be accepted as
observed; no return-based v1.3 adjustment is authorized here. No QC Cloud job
was attempted.

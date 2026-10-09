# Quant + Vision dual-stage v3 — real Windows acceptance (2026-10-09)

## Decision and scope

**D1/D2 engineering PASS; D3 bounded data/UI READY FOR HUMAN TRIAL.** The owner has not authored new v3 labels yet; subjective usefulness is pending first 10–20 cases. No model training, Fusion search, Test/Fresh outcomes or formal QC ran. This is infrastructure readiness, not alpha or trading execution acceptance.

Implementation branch: `quant-vision-dual-stage-v3`, based on GitHub main `52e41714ea115e5556be4483136ae2b5405845bc`. Draft PR #7 (`33c39236d24d7de6855b1f46036044d1dfc181fa`) was selectively ported (16 source/config/test files); its old report and task assets were not rewritten or merged as-is. Native Git HTTPS timed out; authenticated GitHub API sync reconstructed and verified exact Git trees/commits, then fast-forwarded without replacing local data. Publication uses a new implementation PR with its own review. Original #7 remains Draft as historical provenance.

## Actual candidate sample and continuous Q

Reused the verified v1 bundle without choosing on Y: 300 unique securities/windows, 30 hidden repeated tasks, 330 human tasks. New isolated smoke has 10 distinct charts plus one repeat, not human Ground Truth. 44 spaced historical sessions; 219,520 confirmed/probable member security-days inspected, 21,853 unknown membership-days excluded; 163,233 safe 60-day security-days and 290,909 scored windows (60=163,233;126=127,676). Membership/count differences include missing or unsafe windows; no silent survivor-only fallback.

Hidden **sampling-source** quotas: high90 /medium70 /boundary50 /conflict60 /ordinary eligible control30. These are not identical to calculated score categories: controls are sampled from the independent eligible representative frame regardless of score. Actual scored categories in selected windows: high101 /medium82 /boundary55 /conflict61 /control1. Thus do not describe all 30 random controls as low-scoring negative shapes.

Year counts: 2021=33,2022=72,2023=69,2024=64,2025=62. Windows:60=167,126=133; Train238/Validation62; Test/Fresh0. Four credible later-disappeared/acquired anchors participate. 295/300 cross-ID issuer aliases are unverified, retained as uncertainty. 188 windows have accepted minor research uncertainty and six have zero volume at T; these are not certified executable fills. One security/known issuer per unique batch avoids within-security overlap; unresolved alias duplication is not claimed solved.

Q version fuzzy-shape-v1 uses A prior run-up/return and extreme-day concentration, B depth/duration and breakdown penalty, C downside/red-body/volatility compression, D down/up volume and rejection-wick/close-location **proxies**, E short-term green bars/close improvement/local breakout, F last-day gain/rebound/MA distance/recent extension. Initial weights22/18/18/14/14/14%, all disclosed untuned knots in `config/quant_vision_labeling_v1.yaml`; no future optimization or frozen Strategy2 parameter changes. Full aggregate distributions are in the companion JSON. Two-stage representative/hash ranking probabilities are conditional sampling-path probabilities, not market-wide inverse-probability weights. No measured recall, market-wide generalization or unbiased population claim.

## Five contracts, separate Q and secure future boundary

- Strict Pydantic contracts for X_left_num, X_left_svg, H_blind, H_review and Y_future; unknown fields, choices, hashes and versions rejected.
- Existing frozen shape SVG renderer unchanged; new `shape-wrapper-blind-svg-v3` adds anonymous relative percentage scale, T-close cutoff and full candles/volume. NPY is prefix-only 60/126×5 float64, independently hash bound.
- Left SVG is separate from future SVG; no combined hidden plot, shared autoscale or future preload. Future file storage is `.local/` outside existing LS document root. Initial browser API contains no future prices, Y, private identity/date or Quant score.
- Existing Label Studio auth/session and explicit per-view CSRF protection. Persisted H_blind **and** reveal event, same user and namespace required before authenticated right fetch. Missing CSRF403; unauthenticated right302/login; before save/reveal409; foreign task409; direct private path404 and traversal403.
- Append-only SQLite annotations/events; pre-reveal revisions remain blind, first decision preserved. Post-reveal revision requires reason, has separate phase; H_review independent. Retests after any same chart reveal are contaminated and excluded from clean reliability statistics.
- JSON→private Parquet roundtrip: smoke11 blind+11 review+1 post-reveal revision; repeated import identical and no duplicated history. Human0 annotations/events. Wrong task/choice/version/origin/event/revision rejected. Raw export archives keyed by hash; smoke is never a human self-consistency claim.

## Objective Y on actual historical windows

Same source/series/basis selected at T; independent read path to next10 exchange sessions only inside frozen Train/Validation bounds. Hypothetical T+1 vendor-basis opening reference, +5% target/−3% adverse, 1/3/5/10 close returns, MFE/MAE, new-low relative to causal normalized past low translated into reference basis. Fee/slippage both0, explicitly research proxy rather than certified tradable PIT order/fill.

Actual statuses: available234 /ambiguous19 /unavailable31 /censored16. Events: target-first68 /adverse-first149 /neither-hit17 /same-bar-both19 /not-evaluable47. Twelve horizons crossing frozen split bounds were blocked **before** reading outside prices; other19 unavailable next opens and16 later missing/nontrading sessions have no fabricated forward metrics. Flags: opening-gap-target10,opening-gap-adverse17,T+1-vs-T-close gap13; flags may overlap status counts.

Opening gaps after entry have priority over intraday extrema. Both barriers in one bar are ambiguous; only a separately stated conservative adverse-first sensitivity exists. Missing/zero-volume/unsafe price or uncertain membership returns missing/censored; corporate splits explicitly unsupported. These statuses do not establish full delist/halt/action coverage. No Y is used to resample Q or left input; no Historical Test/Fresh price read.

## Executed hard tests and browser evidence

728 full pytest PASS,0 failures/errors/skips,1 existing websockets legacy deprecation warning; `STOCK_RADAR_TEST_LEAN=1` actually executed native LEAN integration. This is compatibility regression, not formal visual strategy QC. JUnit and log remain local.

Hypothesis radically changes future levels with fixed prefix: left SVG bytes, normalized geometry and numeric tensors identical. A deterministic 10× rise vs0.1× collapse fixture also has identical Sharp raster hashes. A Stage A response test mutates both future files and remains byte-identical; another makes all future-file reads throw. Existing Quant causality tests reject T+1 feature influence. Forged IDs, stale revisions, namespace collision, invalid SVG metadata/script/event handlers, future fetch/review before reveal and split boundary reads tested.

All300 actual windows were replayed from the frozen database: raw/normalized hashes, NPY bytes, left SVG, actual future bars/Y and separate right SVG identical. Sharp0.35.5/libvips8.18.7 deterministic left-only rasterization rendered300 images twice to identical PNG bytes; full dependency versions and renderer hashes recorded privately, only aggregates published.

Real Chrome155.0.8059.39 with Playwright, Windows,1440×1100 and1280×900:10 different real charts+1 repeated task. All Observe3/Entry4/Confidence3 choices, reasons multi-select, undo, skip, recent-candle zoom, save→persistent read→reveal→right display→review→refresh→resume checked. **All11 left screenshot before/after pairs have identical SHA256**; actual Y equals prepared private historical data.0 page errors,0 unexpected HTTP failures. Automated labels only smoke; one contaminated repeat excluded,0 clean pairs, no invented human agreement rate.

Found and repaired during real acceptance: LS global CSRF disabling needed explicit protected-view hook; initial chart fit clipped volume; fractional/compositor anti-aliasing changed a few left edge pixels by one color level. Stable line geometry and dedicated left drawing layer resolved it. Failed smoke DBs with6,1,4 mechanical annotations are archived separately; user labels never overwritten. Existing LS out-of-root handler returned500 with an absolute-path error; WSGI guard now normalizes the already forbidden traversal to opaque403. Original valid Pilot local-file route preserved. After guard restart, readonly revealed-chart screenshot equality and20 unretried exports passed.

## Existing behavior and privacy protection

2,623 protected file hashes unchanged: old Pilot/v1 ready/private assets, frozen infrastructure/config/source, Strategy2, frozen core and Fresh databases. Nine old Label Studio project task/data/annotation exports match before/after. Old Pair project has **5 actual user annotations** and was preserved; an older report's zero was historical, not current truth. Existing v1 human projects0 labels. Current v3 human0, smoke isolated. Legacy LEAN/daily-market updater sources unchanged; no scheduled task changed or disabled.

Only source/config/docs/tests and safe aggregate receipts publish. No real PNG/SVG, candles, private security/date/task mapping, label contents, login/session/SQLite or database uploaded. Public evidence includes counts, version/hash proofs and aggregate distributions only; actual screenshots remain local.

## Versions, limits and next owner action

Full config/code/manifest/infrastructure/source-receipt hashes in [aggregate JSON](../evidence/quant-vision-dual-stage-v3-acceptance-2026-10-09.json). Contracts x-left-num-v3/x-left-svg-v3/h-blind-v3/h-review-v3/y-future-v3; left SVG shape-wrapper-blind-svg-v3; raster left-sharp-svg-v3. Font/render dependency changes need explicit renderer version/revalidation.

Formal UI: **http://localhost:8123/quant-review/v3/human/**. [操作说明](../../docs/QUANT_VISION_DUAL_STAGE_LABELING_V3.md). Service is the existing Label Studio with authenticated extension, not a second labeling service. It is an independent route/SQLite namespace rather than a standard LS project ID, because native static tasks cannot enforce a secure post-save future reveal. Old LS project management remains usable. Loopback only, desktop workflow; no mobile support goal.

Same-account cross-namespace reveal is conservatively audited:10 unique browser-exposed windows /11 human tasks are marked contaminated and sorted after clean tasks;290 unique windows remain unexposed. This is not migration of smoke answers into human labels. Live authenticated Human API has0 annotations/events and starts with an unexposed task. Added a regression for cross-origin/per-user exposure; readonly pixel equality retested after the final UI text correction. The wheel includes the HTML resource (built with the existing LS environment setuptools; primary venv lacked the build backend).

Owner should label10–20 charts and judge semantic usefulness before expanding toward50. D3 subjective feedback remains pending. Vision M1/H/Y training requires separate authorization after reviewing true human labels, contamination, missing Y, issuer/time split and input version checks. Stop here.

# Codex Work Order — Implement Quant + Vision Dual-Stage Review v3

> Date: 2026-10-09  
> Work order: **V3-D1/D2/D3 — engineering implementation + real local acceptance**  
> Authority: user-approved [active v3 research plan](../../docs/QUANT_VISION_DUAL_STAGE_RESEARCH_PLAN.md) and [canonical ledger](../../reports/journey-2026-09-30-0651-📌当前总账.md).  
> Do not begin Vision-H/Vision-Y training, Fusion optimization, paid resources, formal QC, Fresh OOS or historical Test tuning without a separate user instruction.

## 0. Read repository and reconcile PR #7 before coding

Repository: `zhoushuming073-cell/stock-radar`  
Primary Windows project directory: `C:\Users\周树铭\Desktop\美股策略研究\stock-radar`

First inspect actual current GitHub `main`, local working tree, recent commits and open Draft [PR #7](https://github.com/zhoushuming073-cell/stock-radar/pull/7) (Quant-guided Human Labeling v1). Its reported implementation commit was `33c39236d24d7de6855b1f46036044d1dfc181fa`; verify it still exists and has not changed. Do not presume the user has zero annotations merely because an older report said so.

Read completely:
- `AGENTS.md`
- `docs/QUANT_VISION_DUAL_STAGE_RESEARCH_PLAN.md`
- `docs/PRICE_STRUCTURE_OUTCOME_LEARNING_PLAN.md` (historical v2)
- `docs/QUANT_VISION_FUSION_RESEARCH_PLAN.md` (historical v1)
- `docs/RESEARCH_INFRASTRUCTURE_V1.md`
- `docs/VISION_LABELING_INFRASTRUCTURE.md`
- `reports/journey-2026-09-30-0651-📌当前总账.md`
- `reports/acceptance/quant-vision-human-labeling-v1-acceptance-2026-10-09.md` on PR #7 branch, if still unmerged
- `docs/QUANT_GUIDED_LABELING_V1.md` on PR #7 branch
- current `radar.vision`, `radar.pit.shape.render_svg`, the Label Studio bootstrap, tests and research-window APIs.

PR #7 was deliberately kept Draft because it conflicted with the prior v2 human-supervision decision. **The user's v3 decision resolves that research intent**: reuse Quant-guided H infrastructure as one part of a **dual-stage H_blind / H_review + separate Y_future design**. Do not simply merge stale PR #7 as-is or overwrite v2 work. Start from fresh `main`, reconcile or selectively port tested source changes, verify that no files/data or existing labels are lost, and open a new implementation PR (or adapt #7 only if its branch is safely rebased and the history/review remains transparent). Never force reset or force-push blindly.

Make a quick brief before changes: active state, open conflicts, safe plan, optional missing dependencies, protected hashes. Work through the stages without needlessly requesting permission at each minor implementation choice; stop and ask if an irreversible or policy-sensitive decision is truly necessary.

## 1. Main deliverable

Replace the unsatisfactory “random blind chart A/B future potential” workflow with **a single SVG-based, two-stage historical decision/review interface**:

**Stage A, pre-reveal**: show the left past-only price+volume SVG through T close. The user submits and freezes `H_blind` (Observe, Entry, confidence and optional reasons).

**Stage B, after persistent save**: load a **different future-only** SVG to the right for T+1 ... T+10 session review, mark hypothetical T+1 open fill, persist `H_review` separately, and display separately computed objective `Y_future` where available.

The visual presentation should be adjacent left/right, with a visible separator at the **information cutoff** T close. Treat actual hypothetical fill on the right at T+1 opening as distinct from the separator. The user's subjective past-only judgment must never be trained as if it saw the right outcome.

For a 10–20 real-image interface smoke run, model training is **not** included.

## 2. Reuse existing data and candidate selection

- Reuse frozen `Research Infrastructure v1` read-only and existing normalized OHLCV windows, PIT/membership gates, provenance and hashes; do not construct another database.
- Reuse PR #7's configurable fuzzy Quant factor A–F logic, sampling, high/mid/boundary/conflict/control groups and 300 +30 historical Pilot **if verification passes**. Preserve original PR7/QVF-v1 local outputs and any user labels as immutable; introduce a new version/namespace/project for v3 if necessary.
- Test/Validation/Fresh isolation as in canonical frozen config; default v3 labeling draws only Train/Validation eligible samples. 295 of 300 PR7 samples reportedly have unverified cross-ID issuer aliases; keep this as a known limitation, not a claim of global issuer dedup.
- No future Y, post-T image, survivor-status hindsight, Strategy2 frozen score or hidden Quant answer may influence the left image, Quant candidate ranking, training inputs or blind human session.
- Preserve ordinary-market controls to estimate candidate selection bias. Q remains a private, separate factor table.

## 3. Five explicit data contracts

Implement versioned, validated schemas, source/renderer hashes, and fail-closed import/export for:

1. `X_left_num`: canonical OHLCV and normalized T-prefix tensor; security identity/date stored **private only**.
2. `X_left_svg`: frozen **left-only** vector chart, SVG/geometry hash; share with Stage A after leak audit.
3. `H_blind`: primary Observe (观察/不观察/不确定), secondary Entry (当前可买/等回落或进一步确认/不买/不确定), confidence high/medium/low, optional reasons, annotation ID, version, time, task hash and initial reveal state.
4. `H_review`: independently versioned **post-reveal retrospective** annotations; never overwrite `H_blind`, label every revision as post-reveal and never count it as blind Ground Truth.
5. `Y_future`: objective outcomes from a separate T+1 onward causal-window generator, with versioned entry reference/horizon, return/MFE/MAE/target-before-adverse, missing/ambiguous flags and hash. This remains private or available only in Stage B; never embed it in Stage A payload.

Also preserve Q factor table separate from all five and audit every linkage through private opaque task IDs. Keep export origin human vs smoke distinct; old Single/Pair and PR7 projects/data unchanged.

**Migration contract**: existing PR7 H labels (if any) remain valid **only as original left-only annotations**, and may be mapped to H_blind only with verified exact security/window/renderer/task mapping and proof the annotator had not seen future. Never fabricate conversion when uncertain. Do not destroy or rewrite revisions.

## 4. SVG and machine input: avoid future leakage through rendering

Existing `radar.pit.shape.render_svg` is under frozen research infrastructure hash/semantic contract. Do not edit it. Add a wrapper/adapter/new renderer version under a non-frozen module.

Stage A displays a zoomable SVG candlestick and volume chart, derived **only** from the T-prefix numeric window. Preserve rightmost candles, wicks, volume and stable formatting, responsive on desktop. No absolute ticker/date, Quant scores or outcome labels in the DOM, task JSON, IDs, SVG metadata or URLs.

Stage B displays a separate future panel, visually aligned beside the frozen left panel, with a clearly differentiated scale and explicit T-close reference / T+1 opening fill marker. A shared y-axis autoscaled by future highs/lows is **forbidden**. The left SVG must not change **one pixel or one normalized SVG path/hash** because of different hypothetical future windows.

Very important: Do not render a full left+right chart and hide the future using CSS. **The Stage A network response, preload, thumbnail, SVG DOM, source-map, JSON API, alt text and accessible metadata must contain zero right-window future values.** The backend must authenticate and gate the Stage B fetch on verified persisted H_blind and reveal event. Stage B must have a separate authorization-checked endpoint and no guessable unauthenticated static future image path. Audit real browser requests before/after reveal.

SVG is for lossless human zoom and optional geometric-learning research. A conventional CNN cannot directly consume SVG XML; later Vision experiments must use either (a) deterministic **left-only** SVG rasterization with renderer hash, or (b) a separately designed vector geometry model. Preserve `X_left_num` for 1D CNN/TCN and independent baselines. Do not claim SVG itself removes all model distortion or quantization error.

## 5. Two-step human workflow with persisted reveal

- Stage A visible questions: Observe, Entry, confidence, optional compact reasons. Save and verify server-side persistence **before** revealing Stage B.
- If Stage A is skipped/unsubmitted, do not emit future right data. Allow later blind decision or explicit disqualification from the clean blind cohort.
- Once revealed, the original blind answer remains immutable as the **first decision**. Later edits carry a post-reveal reason/revision; do not replace the blinded original.
- Stage B review: optional interpretation of setup, poor entry / wrong timing / false break / further selloff / pullback-and-rise / cannot attribute, plus outcome review. No forcing hindsight label to match profitable outcome.
- Persist separate timestamps, audit events (`blind_saved`, `future_revealed`, `review_saved`, `revision_after_reveal`), origin and schema version.
- Repeated charts are needed for consistency, but repeated left windows after their future was revealed are **contaminated retests**. Either schedule repeats before any reveal of the original or mark contaminated explicitly; do not count these as clean blind self-consistency.
- Basic desktop flow: save / next / skip / undo before save / edit with explicit revision / refresh / resume. Do not require re-importing project tasks whenever service restarts.
- Prefer maintainable integration in existing Stock Radar local UI or current Label Studio extension if it can actually enforce server-side reveal. Do not choose an insecure CSS workaround merely to avoid code. Report the chosen UI tradeoffs; avoid cloning a full annotation platform without necessity.

## 6. Objective outcomes generator: limited initial use

Generate Y from **actual** future OHLCV (different read path from pre-reveal) under frozen research split and PIT trust rules. Preliminary target contract from v2: T+1 valid/open entry; horizon H=10 sessions; +5% target versus -3% adverse; additional 1/3/5/10 forward returns, MFE, MAE, new-low, target event day.

Important cases:
- same-day High and Low cross thresholds → `ambiguous`, conservative sensitivity only;
- opening gap through target/adverse barrier → explicitly defined outcome;
- missing next open, halt/delist/merger/price gap/split or uncertain tradability → explicit unavailable/censored/ambiguous, no fabricated fills;
- no target or stop before H end → neither-hit/censored definition;
- calendar vs trading-session lengths, split/price provenance, fees/slippage assumptions and horizon crossing Train/Validation embargo → fail closed or flagged.

Do not compute or expose any Y for Historical Test or Fresh OOS under this task. Keep outcomes separate from H_blind and feature/Q candidate generation. Use on-device local data only, no QC reference data exports, and never leak private candles to GitHub.

## 7. Real tests and acceptance gates (do not claim PASS without execution)

**A — Existing behavior preserved.** Verify no changes to Research Infrastructure v1 frozen semantics/hashes, old P0/P1 Pilot, old user annotations (including any existing Pair and v1 annotations), Strategy2, LEAN, local daily market updates, and Test/Fresh contract. Report before/after comparisons.

**B — Left input is truly isolated.** Construct at least two fixtures with exactly identical T-prefix and dramatically different futures; assert identical left SVG bytes/paths, numerical tensors, image pixels after deterministic rasterization and all Stage A HTTP/DOM responses. Mutate future prices/events and ensure no changes to Quant score or blind tasks. Build negative tests for forged task IDs, unauthenticated right fetch, stale H revisions, right endpoint called before H save, future disguised as SVG metadata, and full-plot autoscaling.

**C — T/T+1 and right chart.** Verify decision cutoff vs next-open fill marker, stable left viewport, future right independent axes, 10-session calendar, gap/delisting/halts/missing session behavior. Verify basic SVG accessibility and real zoom clarity. Make sure right panel reflects actual historical data without altering left.

**D — H/Y segregation.** H_blind, H_review, Y have independent validators, versions, source hashes and strict import/export behavior. Label revision history preserved; smoke cannot enter human truth. A second viewing after reveal is marked contaminated for repeat reliability statistics.

**E — Real Windows browser acceptance.** With actual local market windows, use a real browser (Chrome/Playwright or available alternative) for at least 10 distinct charts. Check initial network has **no future data**, save → verify persistence → unlock right only then → review → refresh → revisit. Test multiple choices, undo/edit, skips, zoom/responsive sizes and export→import. Smoke labels only in isolated test project/namespace. **Human real annotations can only be authored by the user**; report them accurately rather than faking them.

**F — Whole-project regression.** Run full pytest and Native LEAN opt-in when truly available. Report exact tests passed/failed/skipped, browser errors and any remaining limitations. Existing 674 pass receipt is only a prior historical branch acceptance, not a substitute for the current run.

**G — Source and label audit.** Rebuild/replay example sample deterministically and compare hashes, record inference input contract, candidate distribution (high/mid/boundary/conflict/control), years/windows/splits and excluded-data reasons. Accurately report continued PIT/survivorship/issuer-alias deficiencies; do not claim fully unbiased whole US market.

## 8. Deliverables and publishing

- New versioned implementation, config, CLI/UI bootstrap and tests.
- Documented schema for Q / X_left_num / X_left_svg / H_blind / H_review / Y_future, strict future reveal policy, clear T/T+1 entry semantics, supported exceptions and SVG renderer/rasterizer version.
- A real local acceptance report under `reports/acceptance/`, safe machine-readable aggregate evidence under `reports/evidence/`, a short user labeling guide and a canonical-ledger status update.
- Only publish source/config/contracts/tests and safe aggregate metrics. Never push real chart imagery, OHLCV market data, private security/date mappings, Label Studio SQLite database, real labels, sessions or login JSON.
- Open/review implementation PR based on latest `main`; resolve conflicts explicitly (especially Draft PR #7). Re-run necessary local regression after resolving. Merge **only** if all mandatory gates pass and no other author changes are overwritten. On failure leave Draft PR + truthful blockers.

## 9. Stop conditions / output to user

**Stop at:** successful real local D1/D2/D3 readiness, with a URL pointing to the new **left-then-right** labeling workflow and a proposed first 10–20 manually labeled cases. Do **not** invent human labels or start M1, Sequence, LightGBM search, Fusion, formal Historical Test, Fresh or QC.

Final response must include:

1. branch/PR/commit, whether main was updated and whether local main is synchronized;
2. exact local clickable URL and how to start service;
3. whether old PR #7 was ported/rebased/left draft, with reason;
4. sample counts, cases of missing futures, objective-label contract;
5. hard leakage test results, SVG-before-after identity proof and actual browser confirmation;
6. native regression counts and any unresolved limitations;
7. precise first user action, then pause for true human feedback.

If the account is unavailable or local Windows environment cannot be reached, **do not claim local acceptance**. Finish source-only work and report the blocked gates without replacing them with mocks or speculation.
# Box research: consolidated development path

> Revised 2026-10-13. **Planning and acceptance specification only; no detector, labeling, training or backtest authorization.** Read AGENTS → canonical ledger → Research Master Guide → ACTIVE before work. This page revises the existing box path, not the three-family research taxonomy.

## Decision and verified status

The box track now prioritizes **causal, replaceable, open-source-assisted range recognition**; next come independent structure review, a separately defined lower-band rebound rule, and eventually local LEAN validation. A numeric OHLCV CNN/TCN is retained as an optional later comparator, not a required detector or next milestone. S1 market-shock research remains independent.

| Existing artifact | Current role |
| --- | --- |
| [Box/range design brief](../codex/tasks/2026-10-13-box-range-structure-research-design-prompt.md) | Economic intent and later +5% question; design reference |
| [REA-assisted recognition brief](../codex/tasks/2026-10-13-rea-assisted-box-recognition-research.md) | Causal pivot/evidence protocol reference; REA optional |
| [BOX-LQ1 proposal](../codex/proposals/2026-10-13-box-structure-label-quality-v1-1.md) | Label-quality specification; P0/P1 engineering completed in dependent draft PR #24 |
| [S1 proposal](../codex/proposals/2026-10-13-shock-transmission-resilience-s1.md) | Separate backlog; not a box prerequisite |

- Reviewed main: `5165f98b250751ee1a1eea0882ad1980deadf1a8`. Box implementation is unmerged [PR #21](https://github.com/zhoushuming073-cell/stock-radar/pull/21), reviewed head `2a283affeef6336116f5eb8456b914d64bc53f08`. Its partial-history mask defect was repaired and accepted. Preserve the CNN scaffold, but do not make it a detector dependency or redo that fix.
- Dependent draft [PR #24](https://github.com/zhoushuming073-cell/stock-radar/pull/24), reviewed head `b8cd299f33ef2ba9362962b965f08e7bd6e71c85`, completed BOX-LQ1 v1.1 P0/P1 engineering: 722 pytest passed / 18 skipped, ten browser tasks checked, zero formal human labels at that receipt. This means pilot-ready, not established label reliability or detector accuracy. Neither PR is merged into main.
- PR #21's original 30 historical tasks / 90 charts and 719 passed / 17 skipped are dated evidence. Its 70/20/10 sampling remains historical; smoke labels are not Ground Truth. RI v1 begins September 2021, so incomplete monthly history needs observed-length masks. The candidate selector's 126 daily bars and the 42-day close-up display serve different purposes.

## Stage A — open-source selection and detector contract

These are candidates to evaluate, not installed dependencies or declared accuracy winners. Inspect exact license/commit, Python compatibility, dependency and maintenance status, deterministic behavior, runtime, and causal semantics before adoption. No commercial Autochartist, TrendSpider or TradingView internals may be copied.

| Candidate | Reuse assessment | Required local check |
| --- | --- | --- |
| [NumPy quantile](https://numpy.org/doc/stable/reference/generated/numpy.quantile.html) + [SciPy find_peaks](https://docs.scipy.org/doc/scipy/reference/generated/scipy.signal.find_peaks.html) | Transparent quantile-zone and prominence/spacing baseline; reuse NumPy already present | Quantile occupancy is not independent alternation; wrap peaks in T-prefix/confirmation/NaN rules; assess SciPy dependency only during implementation |
| [GregoryMorse/trendln](https://github.com/GregoryMorse/trendln) | MIT-licensed extrema/line candidate; adapter, not schema owner | `findiff`/method compatibility, right-pivot lag and bounded runtime |
| [ednunezg/pytrendline](https://github.com/ednunezg/pytrendline) | MIT-licensed tilted-line comparator for bounded windows | README's exhaustive O(N³) search and old dependencies require benchmarks before universe use |
| [day0market/support_resistance](https://github.com/day0market/support_resistance) | ZigZag/cluster ideas only | No declared license in inspected GitHub metadata; old pinned requirements. Do not copy code/install until license and compatibility are resolved |

Use one versioned `RangeDetector` input/output contract with independent algorithms. Keep `loose_box_v1` unchanged as high-recall retrieval, never a structure label. Record detector disagreements rather than imposing an unmeasured intersection. REA is optional local UI inspection, not a dependency or a route to proprietary algorithm extraction.

The proposed typed result includes detector/config versions, input/source/basis hash, historical identity and membership, decision cutoff `T`, candidate formation start/end, `window_end`, `first_knowable_at`, support/resistance **zones**, width, slope/center drift, independent support and resistance touches, completed alternations, persistence/occupancy, clarity/stability, false-undercut/recovery and breakdown evidence, current normalized position, expiry, uncertainty/rejection reasons, and status `NONE | DEVELOPING | CONFIRMED | BREAKDOWN | UNCERTAIN`. Store `pivot_event_date` separately from `pivot_first_confirmable_date`; a later right-bar confirmation may never be backdated. Developing trailing extrema are provisional.

Represent `structure_exists_in_past` separately from `active_unbroken_box_at_T`. Distinguish horizontal, wide/irregular, local and slowly tilted ranges from incomplete candidates and non-boxes. Structure existence/quality, entry readiness and future rebound outcome are separate objects. Preserve existing 42D / 52W / 48M human views; partial week/month views contain only bars observed through T. Future mutation must leave every T feature/output unchanged. No current-survivor-only historical population or price-basis splice.

## Stage B — six-stock diagnostic acceptance protocol

The following are **user-supplied Alpaca SIP 1Day statistics verified on 2026-10-13**, not newly measured in this docs pass. Old bands are approximate scanner statistics, not actual extremes, support/resistance, confirmed formation intervals or human Ground Truth. Every row is `UNVERIFIED_CANDIDATE`. Actual OHLCV and private labels stay out of GitHub.

| Symbol | Retrospective candidate window | Old statistical band, USD | Alpaca Low min / High max, USD | Daily bars / closes in old band | Diagnostic role |
| --- | --- | --- | --- | --- | --- |
| IREN | 2025-12-26–2026-05-15 | 35.4–59.3 | 30.76 / 65.61 | 97 / 86 | Irregular wide swings; test whether multiple price centers were merged |
| RIOT | 2025-11-21–2026-04-10 | 12.5–17.5 | 11.50 / 19.39 | 95 / 88 | Range candidate; inspect independent alternations |
| APLD | 2025-11-28–2026-05-01 | 23.3–39.0 | 20.00 / 42.27 | 106 / 101 | Wide irregular range; inspect excursions and persistence |
| SOFI | 2026-02-27–2026-08-07 | 15.2–19.6 | 14.88 / 20.13 | 112 / 111 | Relatively clear candidate for first manual inspection, still unconfirmed |
| IONQ | 2025-11-14–2026-01-30 | 40.9–55.6 | 38.00 / 55.66 | 52 / 51 | Local candidate with weak repeated upper-touch evidence |
| POET | 2026-10-07–2026-10-12 | **No reliable band** | 6.40 / 7.60 | **4 / n.a.** | At T=2026-10-12 inspect active-state/breakdown only; four days cannot establish a forming box or prove no earlier box |

Acceptance steps for a **later authorized** implementation:

1. Freeze detector/config/data hashes and this protocol before examining outputs. Feed each detector only the T-prefix. Never hardcode these symbols, old dates/bands or expected labels. Allow other formation intervals/zones and `NONE`/`UNCERTAIN`; keep raw differences.
2. Reconcile Alpaca `feed=sip` statistics with authorized RI v1 price basis, identity, splits/corporate actions and calendar. Record unresolved differences; do not overwrite the frozen database or infer executable fills.
3. Per candidate/T, report independent lower/upper touches with minimum separation, complete U↔L alternations, zone tolerance, center drift, persistence, break/recovery, expiry, pivot event/confirmation dates. Most closes inside an old band do not establish a box. POET tests `active_unbroken_box_at_T` at 2026-10-12; search older history separately and never make four days a global `NOT_BOX` negative.
4. Add trend, crash, one-sided grind, short-history, missing-bar, split/basis and pivot-lag negative fixtures. Post-T bar mutations may not change T outputs.
5. Freeze an **independent blind historical set outside these six symbols**, separated by time/issuer from development and repeatedly discussed cases. Human review is blind to detector scores/old bands. Report false positives, misses, state errors, boundary differences and uncertainty with denominators. The six familiar stocks are regression diagnostics, not independent accuracy/OOS evidence or assumed positives.

Stage B exits with an auditable structure-quality/data-basis report, not a +5% result, confirmed Ground Truth for all six, or permission to use Historical Test/Fresh.

## Revised sequence and stop gates

| Stage | Work when separately authorized | Exit gate |
| --- | --- | --- |
| Completed foundation | Preserve PR #21 labeling/mask and PR #24 v1.1 ontology/browser acceptance; owner-led human pilot remains optional | Verify exact branch dependencies and dated receipts; do not fabricate labels |
| **A — causal detector foundation (next proposed engineering order)** | Due diligence; `RangeDetector`; simple quantile-zone and confirmed-pivot baselines; optional bounded library adapters; historical as-of-T search | License/compatibility/runtime receipt; deterministic, future-mutation and first-confirmable-date tests; permitted historical scan with exclusions/denominators |
| **B — diagnostic and independent quality** | Six specified unconfirmed cases, pre-frozen blind audit, RI v1 basis reconciliation, independent human structure review | Error/ambiguity/coverage report; freeze version before blind evaluation |
| **C — lower-band rebound rule** | Position, stabilization/exhaustion, volume/strength, headroom, entry/exit/invalidation rules | No future outcome in box definition; freeze rules/time cutoffs before Y |
| **D — outcomes and local LEAN** | Separately authorized Train/Validation +5% and adverse/horizon study; trusted-data local LEAN with T+1 tradable entry and costs | Honest denominators and explainable fills; Test/Fresh and QC separately gated |
| **E — optional ML comparator** | After credible rule baseline, consider logistic/LightGBM/CatBoost; keep old CNN/TCN as optional sequence control | Incremental value under same population/split/outcome/cost contract |

The next **proposed** executable work order is Stage A only: inspect PR #21/#24 without merging, freeze schema and versions, check candidate libraries, implement two bounded causal baselines, add fixtures and a real permitted-history runtime/coverage receipt. Stage B cases may be prepared as diagnostics but no human answer is hardcoded. Stop before new-case labeling, future-return evaluation, strategy signals, LEAN/QC or Test/Fresh. Stage A requires a later explicit owner instruction and ACTIVE update; this docs-only PR does not activate it.

S1 stays deferred and independent. Preserve earlier proposals, model scaffold, reports and local data; never rewrite historical acceptances. This consolidated path belongs to [PR #23](https://github.com/zhoushuming073-cell/stock-radar/pull/23); implementation PRs remain reviewable dependencies.

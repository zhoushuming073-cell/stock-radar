# Research database reliability scorecard — Research Infrastructure v1 vs legacy baseline

> **Date:** 2026-10-10  
> **Status:** ARCHIVED RESEARCH JUDGMENT / NOT AN ACCEPTANCE GATE  
> **Purpose:** Preserve the current comparative judgment of how trustworthy the finalized local research database is for experiments, relative to the older current-survivor-oriented local research path.

## 1. What is being compared

**New baseline:** finalized **Research Infrastructure v1**, using `shape_research_universe_v1(root)`, frozen core + Fresh sidecar, historical membership reconstruction, explicit security identity boundaries, quarantine/missingness semantics, and version/hash locking.

Primary evidence:
- `reports/acceptance/research-infrastructure-v1-finalization-2026-10-08.md`
- `docs/RESEARCH_INFRASTRUCTURE_V1.md`
- `reports/acceptance/pit-acceptance-2026-10-07.md`
- canonical ledger.

**Legacy baseline:** the pre-finalization local historical research path centered on current-active/current-survivor-oriented populations and older phase2/market stores. This is a conceptual baseline for comparison, not one single file hash. Do not confuse it with the later strict PIT audit stores.

The new infrastructure **reduces survivorship bias materially but does not eliminate it**.

## 2. Score interpretation

These scores are a research judgment, not measured probabilities and not formal acceptance metrics.

Scale:
- 90–100: strong for local research use;
- 80–89: good, with known caveats;
- 70–79: usable but material limitations remain;
- 50–69: exploratory only;
- <50: weak for historical inference.

Weighted overall score:

`overall = sum(dimension_score × weight) / 100`

## 3. Multidimensional scorecard

| Dimension | Weight | Research Infrastructure v1 | Legacy baseline | Gap | Reason for the gap |
| --- | ---: | ---: | ---: | ---: | --- |
| Historical universe / survivorship control | 20% | **82** | **28** | **+54** | New path uses dated membership reconstruction and retains later-disappeared securities; legacy research could inherit the current-active cohort. Residual missing disappeared-security history prevents a bias-free claim. |
| Security identity / ticker continuity | 12% | **84** | **38** | **+46** | Stable IDs, dated ticker episodes, reuse isolation and known identity-conflict quarantine are explicit. Legacy symbol-centric history had much greater reuse/continuity risk. |
| Price/window coverage for research | 12% | **84** | **70** | **+14** | New supported safe-candle/window coverage is broad and versioned, but missing historical sessions remain material for disappeared names. Legacy data could be plentiful for survivors while weaker for historical population completeness. |
| Corporate actions / terminal economics | 8% | **74** | **55** | **+19** | Split handling and event/identity isolation improved substantially. Complete merger, bankruptcy, conversion, delisting payout and terminal-wealth treatment are still not fully certified. |
| Causality / future-leakage controls | 12% | **96** | **80** | **+16** | New API explicitly clips inputs/benchmarks at T, blocks future metadata/labels, and separates Fresh evaluation rules. Earlier feature paths already had causal work but with less unified enforcement. |
| Missingness / quarantine transparency | 10% | **94** | **58** | **+36** | Missing, unknown and quarantined states remain explicit rather than silently promoted or discarded; conflict reasons are retained. |
| Reproducibility / version locking | 10% | **97** | **75** | **+22** | Frozen semantic hash, database hashes, source manifests, rules/code locks and deterministic window exports make the new path much more reproducible. |
| Shape / Quant / Vision experiment usability | 8% | **92** | **72** | **+20** | Stable causal window API, normalized tensors/SVGs, supported historical universe and Fresh sidecar make it much better suited to repeated rule/shape/vision experiments. |
| Portfolio execution realism | 5% | **60** | **48** | **+12** | Data inputs are better, but exact fills, auctions/minute path, full terminal economics and some absolute historical liquidity/execution evidence remain incomplete. This is still not broker-grade or certified execution history. |
| Fresh / OOS readiness | 3% | **88** | **35** | **+53** | New Fresh decision semantics allow pre-F lookback while enforcing T-only inputs and requiring real freeze receipts for formal evaluation. Legacy path did not have a comparably clean Fresh contract. |

### Weighted total

- **Research Infrastructure v1: 86.1 / 100**
- **Legacy baseline: 55.1 / 100**
- **Weighted gap: +31.0 points**

## 4. Practical interpretation

### A. Shape / candidate-generation research

**Research Infrastructure v1: about 90/100 practical confidence.**

It is now appropriate as the default local data backend for:
- Q1/Q2 rule research;
- causal feature experiments;
- chart/shape retrieval;
- Vision dataset preparation;
- candidate funnel diagnostics;
- comparative strategy research before formal external validation.

This does **not** mean the resulting strategy is good. It means the data plumbing is sufficiently credible for local research questions.

### B. Historical portfolio-return inference

**Research Infrastructure v1: about 65–70/100 practical confidence.**

The database is substantially better than the legacy path, but portfolio return should still be described as exploratory because:
- later-disappeared research-qualified securities still have missing sessions;
- complete terminal economics are not certified;
- absolute liquidity and some corporate-action semantics are not broker/exchange-grade PIT;
- daily Open/Close proxies are not exact execution.

Therefore a local LEAN result can answer **"is this strategy worth further study?"** more reliably than before, but not **"this is the unbiased investable historical return."**

### C. Formal / publication-grade historical claims

Current score: **below the threshold for a bias-free claim**.

The project must continue to say:
- survivorship bias is reduced, not eliminated;
- General PIT remains an audit/deep-investigation layer;
- QC/other independent data may later serve as external validation;
- no local result alone proves alpha.

## 5. Repository evidence behind the score

Key facts from the finalization report:

- Research Infrastructure v1 status: `RESEARCH_INFRASTRUCTURE_V1_FROZEN`.
- Combined technical readiness: **5,811,586 / 6,929,009 observed common ID/sessions = 83.8733%**.
- Default supported safe candles: **5,407,961**.
- Historical IDs with any safe candle: **8,823**; default supported IDs: **8,773**.
- Supported 126-session research windows: **4,256,368**.
- Research-relevant later-disappeared securities: **2,212 IDs**.
- Their safe sessions: **802,380 / 1,250,196 = 64.1803%**.
- Their missing sessions: **443,997 / 1,250,196 = 35.5142%**.
- 126-session supported-window coverage among that research-relevant disappeared cohort: **1,462 / 2,212 = 66.0940%**.
- Quarantined sessions are retained explicitly rather than silently converted to valid data.
- Fresh 20/40/60/126 supported decision windows: **34,491 / 33,745 / 32,979 / 30,462**.
- Research Infrastructure v1 semantic hash: `74b765911a8a4f18b2074cd8d9e529b25b54afade15309a148b0ca43340b80be`.
- Final native-inclusive infrastructure regression: **595 PASS, 0 failed, 0 skipped**.

These numbers explain both sides of the score: the new infrastructure is much stronger for research, while disappeared-security missingness and terminal/execution limitations still cap formal historical-return confidence.

## 6. Decision record

For new local historical strategy/plugin/shape/Vision experiments, the project default is:

> **Use Research Infrastructure v1 / `shape_research_universe_v1`.**

Do not silently revert to a current-survivor historical population merely because it is easier to run.

Existing historical Runs keep their original provenance and should not be re-labeled as Research Infrastructure v1 results.

This scorecard should be updated only if the database semantics, coverage, or evidence materially changes. Strategy performance by itself is **not** a reason to raise or lower the database reliability score.

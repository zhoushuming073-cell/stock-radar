# Research Proposal S1 — Market Shock Transmission, Relative Dislocation & Resilience

> Date: 2026-10-13
> Status: **PROPOSED / NOT ACTIVE / NOT AN IMPLEMENTATION AUTHORIZATION**
> Research family: **Quant-only** (an independent S1 subproject; NOT a fourth research family).
> Dependency: frozen Research Infrastructure v1 on main. **Independent of** Box Labeling v1, PR #21, Q1/Q2/Strategy 2 and Vision training.
> Authority: `AGENTS.md` → canonical ledger → `docs/RESEARCH_MASTER_GUIDE.md` → `codex/tasks/ACTIVE.md`. This document does not replace the active Box labeling work order.
> Activation: an explicit user instruction plus ACTIVE update is required before implementation, forward-outcome studies or models. This commit alone only preserves the proposal.

## Codex research mandate

Act as an empirical asset-pricing researcher and data-integrity engineer, not a backtest optimizer. Test the competing mechanisms of **temporary liquidity-driven price pressure** vs **persistent information-driven repricing** following a common market/peer negative shock. The distinction **cannot be inferred causally from OHLCV alone**. Until independently dated news/event data exist, call it a *price-dislocation proxy*, not a verified "mispricing", "forced selling", "nonfundamental shock", or "sentiment panic."

### Primary falsifiable hypothesis

H1: Conditional on negative common-market or peer shocks, a stock's **historically risk-adjusted idiosyncratic return residual**, interacted with pre-shock volatility, turnover/volume proxy, peer-shock breadth and market state, predicts the distribution of **5/10-session future relative returns and downside risk** more reliably than unconditional reversal, market-beta and peer-reversal baselines.

H0: the residual and interactions add no reproducible **out-of-sample** information after risk factors, time dependence, data-quality restrictions, and multiple-testing adjustments.

Be prepared to **reject H1**. Signal discovery is not evidence of free alpha, and the historical authors' findings at a *monthly* horizon do not validate a 5-day prediction.

### Mechanism hypotheses to compare, not assume

- M1 temporary price pressure: broad peer selling plus unusually negative idiosyncratic residual, followed by partial reversal.
- M2 information persistence: sustained earnings/industry news risk and high news-linked trading, followed by continuation.
- M3 common factor compensation: apparent rebound explained by high beta and changing volatility, not idiosyncratic alpha.
- M4 selection/survivorship artifact: a rebound arises mainly from incomplete disappeared-stock coverage, invalid price basis, omission of terminal events or a few highly correlated shock days.

Each mechanism must have an observable proxy, competing explanation, and a test that could falsify it. Never label an event as M1 or M2 "true" from its future return.

## Scientific references and bounded interpretation

1. De Bondt & Thaler (1985), *Does the Stock Market Overreact?*, **Journal of Finance**. Behavioral overreaction evidence in long-horizon winner/loser portfolios. Richard Thaler received the 2017 Nobel economics prize; the paper was **not itself awarded a Nobel**. **No direct 5-day inference.** https://doi.org/10.1111/j.1540-6261.1985.tb05004.x
2. Engle (1982), *Autoregressive Conditional Heteroscedasticity with Estimates of the Variance of United Kingdom Inflation*, **Econometrica**. Conditional volatility as a state variable. Engle received the 2003 Nobel economics prize. https://doi.org/10.2307/1912773
3. Nagel (2012), *Evaporating Liquidity*, **Review of Financial Studies** (NOT Journal of Financial Economics). Short-term reversals as a liquidity-supply return proxy; stress dependence. https://doi.org/10.1093/rfs/hhs066
4. Hameed & Mian (2015), *Industries and Stock Return Reversals*, **Journal of Financial and Quantitative Analysis**. Within-industry reversal in monthly returns; common stress interaction. https://doi.org/10.1017/S0022109014000404
5. Chiang, Kirby & Nie (2021), *Short-term Reversals, Short-term Momentum, and News-driven Trading Activity*, **Journal of Banking & Finance**. News-related activity can change the sign of short-horizon relationships; turnover is not a pure liquidity measure. https://doi.org/10.1016/j.jbankfin.2021.106068
6. Cohen & Frazzini (2008), *Economic Links and Predictable Returns*, **Journal of Finance**. Demonstrates economic customer-supplier links, **not** that rolling price correlation proves a commercial link. https://doi.org/10.1111/j.1540-6261.2008.01379.x
7. Gu, Kelly & Xiu (2020), *Empirical Asset Pricing via Machine Learning*, **Review of Financial Studies**. Nonlinear interactions justify later comparison, not immediate GNN or deep-learning investment. https://doi.org/10.1093/rfs/hhaa009
8. Fama (1970), *Efficient Capital Markets: A Review of Theory and Empirical Work*, **Journal of Finance**. Strong null benchmark: historical-looking effects may disappear after costs/controls. https://doi.org/10.1111/j.1540-6261.1970.tb00518.x

Use linked publisher/DOI/NBER material, distinguish papers and mechanisms, and do not state that Nobel awards validate short-term trading forecasts.

## Repository-grounded constraints before any research

- Use `shape_research_universe_v1(root)` and Research Infrastructure v1 as the default **read-only, date-bounded historical universe**. `market.duckdb` is an operational current-market source, not an automatically acceptable historical membership baseline.
- Inspect `docs/RESEARCH_INFRASTRUCTURE_V1.md`, `docs/SHAPE_RESEARCH_DATA_LAYER.md`, `docs/RESEARCH_PARAMETER_CONTRACT.md`, original split contracts and existing LEAN receipts **before** choosing any events or labels.
- Frozen price-history snapshot begins September 2021. **Do not claim COVID March 2020 coverage** or backfill nonexistent historical context.
- Known research-qualified later-disappeared securities still lack approximately **35.5% of observed-session coverage** in the 2026-10-08 RI v1 snapshot. This is a material tail-event/survivorship limitation. State observed universe denominators, missingness, membership unknown and safety quarantines at all stages.
- OHLCV is split-normalized for many sources. Scale-free returns may be usable after strict source/basis consistency checks, but **do not use a normalized candle as a tradable absolute raw open**. An executed/terminal-value total-return study needs independently safe executable prices, corporate actions and exit economics.
- Current fixed Test was previously inspected in other research; available Fresh data were inspected and **do not magically become pristine OOS after a new model is invented**. A legitimately untouched forward-live evaluation period must start after genuine model/parameter freeze.
- Existing QC Cloud/account access is explicitly on hold following a policy warning. **No Cloud retries, scraping/export workarounds, broker requests, purchases or trading.**

## Proposed work packages (gated; STOP when data are insufficient)

### S1.0 — Historical feasibility and data-coverage decision (**mandatory first**)

Build a **read-only availability audit**, not a forecast model. For each eligible decision date and security:
- verify `security_id`, dated membership and listing/exit evidence, price source, adjustment basis, missing/quarantined days, benchmark overlap, min lookback, historical open availability and total-return limitations;
- compute usable observation counts and *independent* common-shock dates by year, market regime, liquidity tier and history length; separate raw/security-days from disjoint calendar-event clusters;
- audit full-market peer taxonomy: if historically valid industry membership is unavailable, do NOT use today's industry code retroactively. Allow a **rolling pre-T return-similarity graph** as a statistical association, clearly labeled a proxy;
- quantify missing and exit-linked sample sensitivity, alternative unknown-member inclusions, and primary reference return availability;
- explicitly assess whether enough event clusters exist across Train and Validation for a 5/10-day exploratory study without Test/Fresh lookahead.

Output `GO_FEASIBLE / CONDITIONAL_WITH_LIMITS / NO_GO_DATA_BLOCKED`. If NO_GO, **do not** synthesize events, loosen integrity checks for more signals, or run a profitable-looking backtest.

### S1.1 — Versioned event definition and exposure estimation

Propose **before reading future outcomes** a family of bounded negative-event criteria: market/peer drawdown or standardized surprise, peer breadth and unusually low stock residual. Event-day T close is the earliest decision point for inputs containing T's closing price/volume; earliest tradable hypothetical entry is a valid T+1 open.

Recommended research row key:
`(security_id, decision_date, event_rule_version, data_snapshot_hash)`.

Store source lineage and coverage, history length, missingness, candidate funnel, shock strength and repeat-group ID. Keep feature tables and forward outcomes in **separate stores**.

Risk adjustment start point (illustrative, not a locked final estimator):

~~~text
r_it = alpha_i,t-1 + beta_m,i,t-1 * r_market,t
                      + beta_p,i,t-1 * r_peer_ex_i,t
                      + epsilon_it
~~~

- Estimate beta, intercept, peer membership and peer weights **using information known no later than T-1**; T returns are observed at T close. No contemporaneous T-linked graph construction in T prediction.
- Peer index must exclude self, overlapping duplicates and lookahead membership; robust min peer count, rolling-window dependence controls and explicit uncertainty.
- Measure historical volatility/regime and price-volume surprise causally; any `ADV` or `turnover` must distinguish raw-share quantity, adjusted volumes and unknown share-float denominators.
- Provide both factor residual and deliberately simpler unadjusted peer-relative return. Do not infer “fair value” from either.
- Record whether a peer graph actually adds out-of-sample signal over market/industry simple baselines; do not automatically move to GNN.

Stress grids and thresholds are predeclared and fixed from Train-only empirical distribution. Report multiple specifications and correct for data-mining; **never tune thresholds to target attractive observed winners**.

### S1.2 — Outcome policy, common controls and blind model splits (separately authorized phase)

Only after S1.0 feasibility and owner authorization to examine forward outcomes, create:
- primary response: 5-session **risk-adjusted post-entry return** starting from earliest safe T+1 open, using a precisely declared terminal price/date and executable-price contract;
- secondary: 10-session response, maximum adverse excursion, missing/halts/delist/censored statuses, and model-free signed residual continuation;
- separate `observed`, `censored`, `unavailable`, `ambiguous` counters, **no missing=zero**;
- matched controls by pre-event beta, momentum, recent volatility, volume/liquidity and calendar date, selected only from T-known inputs. Avoid matching on post-T observables;
- if trusted tradable T+1 opens or terminal outcomes are missing, fall back **only to explicitly labeled descriptive adjusted-close response** and mark the executable strategy study BLOCKED. Never advertise it as tradeable P&L.

Use strictly time-ordered research splits aligned to repository contract. Apply at least horizon-aware purge/embargo, same-issuer/day cluster protection, no cross-split repeated event leakage. Previously inspected Historical Test/Fresh **cannot** be presented as untouched validation. Reserve the first genuinely new, post-freeze live period for true OOS.

### S1.3 — Econometric baselines before ML (separately authorized phase)

Pre-register comparators:
- unconditional post-shock mean, market-adjusted benchmark;
- simple short-term reversal;
- beta + momentum + realized volatility;
- same-day peer-relative reversal;
- peer-relative reversal + regime/liquidity/volatility interactions;
- only then penalized GLM/GBDT and optional dynamic-graph extension.

Statistical tests must account for cross-sectional common-date clustering, same-security serial dependence, overlapping holding windows and heteroskedasticity (e.g. date/security block bootstrap or defensible multi-way clustering). Report sample sizes in **distinct events/dates/securities**, not just security-day rows. Include calibration and confidence intervals, not just return win-rate.

Report Train vs Validation separately with precommitted hyperparameter budget, no backtest-driven silent revisions, sensitivity by market stress, liquidity, missing membership, peer construction and cost schedules. Check whether claimed improvements persist after matching, costs and excluding the most influential event clusters.

### S1.4 — Advanced research extensions (**DESIGN ONLY; future gate**)

Only if S1.3 finds stable incremental predictive information:
- replace simple return-similarity peers with **publication-PIT economic links** (supplier/customer) when trustworthy timestamped sources exist;
- add historical publication-time news/earnings semantics to disentangle price-pressure proxies from potentially persistent information;
- compare rolling correlation network, graph centrality and dynamic relational encoders with strong non-graph baselines; do not assume causal diffusion from correlations;
- assess heterogeneous treatment of market-wide versus industry-specific shocks and robustness across independent eras.

No GNN, broad data purchase, news scraping or large-scale training in the proposed first work package.

## Anti-leakage and validity checklist (must be executable tests)

1. **T-boundary:** changing every OHLCV row >T must not change event inclusion, peer set, betas, feature matrix, hashes or visible data.
2. **Peer causality:** graph/peer weights from historical estimation window ending by T-1, no self-edge, no use of future delisting or realized outcomes.
3. **Corporate actions:** deterministic source/basis compatibility; price scale and split tests; adjustment mismatches fail closed.
4. **Denominator honesty:** known/probable/unknown members, missing/censored outcomes, unavailable retired stocks and full vs eligible universe reported separately.
5. **Research independence:** independent impact-day clusters, time/issuer leakage controls, mutually isolated candidate feature and outcome stores.
6. **Statistical discipline:** selected thresholds frozen before outcome inspection, negative controls/placebo periods, multiple-testing acknowledgement; no cherry-picked headline win rate.
7. **Security/privacy:** data stores, real security mappings, paid/API tokens and raw outputs remain ignored local; only aggregated evidence, code and versioned specs committed.
8. **Execution boundary:** no simulated next-open fill unless independent tradable prices exist; full official LEAN / QC remains a **separate** gate.

## Scope of the first authorization (suggested, NOT yet granted)

If the owner activates the first S1 task, execute **S1.0 only**, and optionally a *feature-only* non-predictive S1.1 after the feasibility decision. **Do not generate forward Y, train outcome models or run profitability evaluations** without a subsequent explicit work order. This prevents accidental reuse of inspected outcomes as purported untouched evidence.

Expected outputs after authorization:
- `docs/SHOCK_RESEARCH_S1_DATA_CONTRACT.md` covering causal event/peer/return definitions and hard provenance gates;
- `reports/acceptance/shock-s1-feasibility-<date>.md` with raw counts, valid distinct event clusters, failure rates, sensitivity and GO/NO_GO; no falsified acceptance;
- `reports/evidence/shock-s1-coverage-<date>.json` containing **aggregate** diagnostics only;
- small pure-functional feature prototype/tests **only if** audit establishes safe inputs and the active scope allows them;
- a reviewed PR and short handoff: exact data read, code/test results, uncertainty, proposed next gate and what was explicitly **NOT_RUN**.

Success of S1.0 means a reproducible, honest **feasibility decision**, including a credible NO_GO. It does **not** mean predictive alpha was discovered.

## Owner activation example (not effective until expressly approved)

“Authorize S1.0 Shock Transmission feasibility as the ACTIVE Codex task. Update `codex/tasks/ACTIVE.md` and the canonical ledger scope pointer. Use `codex/proposals/2026-10-13-shock-transmission-resilience-s1.md`. Keep Box proposal and previous active work preserved; do not inspect future returns or access QC.”

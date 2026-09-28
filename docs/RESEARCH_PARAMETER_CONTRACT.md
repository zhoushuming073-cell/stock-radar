# Research parameter contract

Stock Radar uses five namespaces. A new run records the resolved `strategy`,
`evaluation`, `execution`, and `dataset` objects and a source for each leaf.
`view` is local presentation state and is excluded from the research hash.
Historical runs retain their original metadata and are never reinterpreted.

## Boundaries

| Namespace | Owns | Does not own |
| --- | --- | --- |
| `strategy` | Causal hard filters, scores, ranking, optional strategy output cap | Future labels, fills, cash |
| `evaluation` | Forward-label definition, Top-K, event deduplication, statistics | Candidate generation |
| `execution` | Initial cash, intake cap, gaps, sizing, liquidity, fees, slippage, market guard, exits | Strategy signals |
| `dataset` | Split/window, feature and label versions, data snapshot, historical universe and provenance | Scoring rules |
| `view` | Display Top-K, playback pace, panel, page size | Any persisted result or research hash |

Resolution order is host default, then strategy default, then explicit run
override. A leaf's source is `host_default`, `strategy_default`, or
`run_override`. The complete resolved value and source map are stored with a
new run before a worker starts. Validation rejects unknown override paths.

## Audited parameter map at baseline `34f32f9`

| Old location / name | Classification | Canonical path / treatment |
| --- | --- | --- |
| Plugin thresholds and component weights | strategy | `strategy.*`; Strategy 2 weights were Python constants |
| `max_new` in Strategy 2 | conflicting strategy/execution | Legacy intake hint; new `execution.max_new_positions_per_day` |
| `selection.max_candidates` | strategy | `strategy.selection.max_candidates`; `null` means no truncation |
| Scanner `max_candidates` request | conflicting evaluation/strategy | Replace with `evaluation.top_k_values`; no candidate truncation |
| `max_new_candidates` in backtest YAML | execution | `execution.max_new_positions_per_day` |
| Hard-coded 5/10/20 in Scanner metrics/UI | evaluation/view | `evaluation.top_k_values` for metrics; `view.display_top_k` for display |
| `take_profit`, `stop_loss`, `max_holding_sessions`, strategy `exit.*` | execution | `execution.exit.*`; nullable, host-executed |
| `initial_capital`, entry-gap limits, allocator, sizing fractions, ADV participation, slippage, market guard, execution timing | execution | `execution.*` |
| Fee profile and cost schedule | execution / integrity lock | Host-owned fee schedule identified by version/hash; plugins cannot bypass it |
| Scanner horizon, upside targets, downside targets, explicit primary target and primary adverse target, falling-knife threshold | evaluation | `evaluation.*` |
| Success rule, Top-K, event cooldown | evaluation | Explicitly resolved, never passed to plugin context |
| Train/Validation/Test, signal/evaluation dates, versions, database snapshot | dataset | `dataset.*` |
| Universe membership and dated symbol map | dataset | `dataset.universe_mode` and provider fingerprint |
| Daily playback delay and UI Top-K selector | view | `view.*`; never changes research hash |
| Feature engineering weights/window and split fractions/embargo | internal or dataset | Versioned host feature pipeline and dataset split; not strategy controls |
| Source/code hashes, causal whitelist, fill/accounting invariants | integrity_lock | Host-owned, immutable and never plugin-configurable |

## Important semantic distinctions

`strategy.selection.max_candidates` may truncate a strategy's own ranked
output. Scanner evaluation Top-K does not change generated candidates.
`execution.max_new_positions_per_day` caps simulated entries and cannot change
Scanner storage or labels. Legacy `max_new`, `max_new_candidates`, and Scanner
`max_candidates` remain readable in old runs; new requests issue explicit
compatibility warnings where they are accepted.

Scanner reports both observation Precision/Lift and event Precision/Lift at
each configured `evaluation.top_k_values` rank. The primary path-dependent
outcome uses the exact configured `evaluation.primary_target` and
`evaluation.primary_adverse_target` pair; no nearest-threshold inference occurs.
Event metrics take raw daily rank ≤ K, then remove cooldown-repeat signals,
without refilling Top-K. They divide by the same eligible-market observation
base rate. Observations remain stored. In PIT mode, cooldown follows stable
`security_id` across ticker changes. Market-regime success rates use the
configured `primary_outcome`, including target-before-adverse when selected,
and omit ambiguous outcomes. Candidate, background, and event censoring counts
and rates expose unavailable outcomes. PIT membership plus these diagnostics
does not substitute for a proper delisting-return/terminal-value data policy.

New research backtests default to `execution.timing: next_open`: a close-based
exit trigger executes at the next session Open. The explicit `legacy_close`
compatibility mode executes such exits at that session's Close, while entries
still follow the engine's next-session Open rule. Historical metadata without
a timing field retains its compatibility fallback.

Experiments can grid-search declared strategy fields and Scanner evaluation
fields on Train/Validation. Scanner ablations are supported; rolling-window
experiments currently execute backtests only. Test remains excluded from
parameter search.

`current_snapshot` is the baseline universe mode. It means historical
membership may be missing delisted, renamed, or bankrupt securities.
Its runs must show **Survivorship Bias Risk: Present**. Point-in-time mode
requires an imported historical security master and interval coverage; a
current Alpaca asset snapshot cannot provide that evidence.

## Strategy 2 hidden-assumption audit

| Assumption at baseline | Value | UI level |
| --- | --- | --- |
| Prior-strength scale upper bound | 0.50 | advanced research |
| Ideal pullback depth / score width | 0.18 / 0.22 | advanced research |
| Main score weights: prior, pullback, exhaustion, support, new-low, reversal, not-extended | .15/.20/.15/.15/.10/.20/.05 | advanced research |
| Exhaustion weights: slowing decline, red-body contraction, range contraction | .50/.25/.25 | advanced research |
| Absorption component weights | Four equal .25 parts | advanced research |
| Early reversal component weights | Four equal .25 parts | advanced research |
| Not-extended component weights | Three equal 1/3 parts | advanced research |
| Hard-filter thresholds already in strategy YAML | See `strategies/full_strategy2_v1/strategy.yaml` | core or advanced by schema |

The weights above remain hard-coded in
`src/radar/strategy/full_strategy2.py`. They are causal scoring assumptions;
changing them creates a new strategy hypothesis and changes the recorded code
hash. They are not run overrides yet and do not belong in the default Scanner
control row. Promoting them to YAML later requires a reviewed version change.

## UI schema and compatibility

`src/radar/lab/schema.py` explicitly defines each visible control's path,
meaning, unit, bounds, level, mode, and default. The browser does not turn
arbitrary YAML scalars into inputs. The built-in Strategy 2 has declared
controls; an imported v1 plugin without a declared host schema remains
readable and runnable with its installed defaults. Its run draft can be edited
as validated JSON in a collapsed panel. The v1 plugin interface has not been
expanded.

New runs persist `resolved_config` (values, leaf sources, hash). Old completed
runs keep their legacy metadata and are not recalculated or relabeled.
The scanner's old request field `max_candidates` is accepted only as an
explicit, deprecated strategy output cap. New UI requests do not send it.

## Research integrity locks

Plugins receive a date-bounded causal context, never future OHLC, labels,
equity, account state, database connections, or order/fill APIs. Host code owns
forward labels, execution, fees, slippage, portfolio accounting, persistence,
and hashes. Source inspection is a guard against known unsafe code, **not** an
operating-system sandbox for untrusted Python plugins; install only trusted
plugin code.

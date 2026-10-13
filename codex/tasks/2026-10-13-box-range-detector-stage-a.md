# Stage A work order — causal box/range detector foundation

> Owner authorization: 2026-10-13, explicit “授权” in response to the
> proposed Stage A development. Status: **ENGINEERING COMPLETE ON DEPENDENT
> BRANCH; NOT MERGED**. This file records the scope actually authorized and
> implemented; it does not activate Stage B.

Authority: AGENTS → canonical ledger → Research Master Guide → ACTIVE → this
work order. The revised [planning PR #23](https://github.com/zhoushuming073-cell/stock-radar/pull/23)
sets the box route. Code depends on unmerged PR #21's repaired base and
dependent PR #24's v1.1 labeling foundation. Preserve those historical
acceptances and do not copy/merge their changes into main implicitly.

## Authorized scope

1. Inspect open-source licenses/dependencies/maintenance and select a bounded
   reusable baseline. No proprietary charting-system internals.
2. Define one versioned, replaceable `RangeDetector` input/output contract.
   Keep `loose_box_v1` unchanged as a retrieval comparator, not Ground Truth.
3. Implement a simple quantile-zone and confirmed-pivot-zone detector. Search
   historical completed windows through T; separate historical existence from
   active unbroken state. Record event date and first confirmable date.
4. Add causal, negative, breakdown, expiry, input-safety and deterministic
   tests. Run the full project regression.
5. Run a bounded **read-only** diagnostic scan using real eligible
   Train/Validation Research Infrastructure v1 history. Publish aggregate
   denominators, exclusions, statuses, disagreements and runtime only.
6. Document risks and Stage B handoff without changing the frozen RI v1
   database or any human label store.

## Exit gate

The engineering gate is met when both algorithms share the contract, post-T
mutation and pivot-delay tests pass, a real-history diagnostic receipt exists,
and full pytest passes. This is **not** a box-accuracy, human-reliability or
profitable-strategy gate. The six familiar Alpaca candidates and an independent
blind set belong to separately authorized Stage B. No new labeling, ML
training, future-outcome use, Historical Test/Fresh development, signals,
LEAN/QC run, broker action or main merge is authorized here.

Implementation/limitations: [detector guide](../../docs/BOX_RANGE_DETECTOR_STAGE_A.md).
Evidence: [Stage A acceptance](../../reports/acceptance/box-range-detector-stage-a-2026-10-13.md).

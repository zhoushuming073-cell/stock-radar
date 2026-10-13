# Box Structure Human Labeling v1.1 — pilot handbook

The v1.1 route is `http://localhost:8124/box-label/v1.1/human/` when this code is running on the local Label Studio service. Authentication is the existing local Label Studio login. The first engineering checks use `/box-label/v1.1/smoke/`; smoke and human revisions have separate SQLite files. The v1.1 route presently reads the **existing immutable 30-task v1 manifest**, while keeping v1.1 labels in `annotations-v1.1-{human|smoke}.sqlite3`. The old v1 route and its `annotations-{human|smoke}.sqlite3` remain intact. This is an **ontology/reliability pilot**, not a representative recall or model training set. The new candidate-pool contract is in `config/box_labeling_v11_sampling.yaml`; no 180-task pool is claimed to exist yet.

## What to judge

All three charts end at the same historical decision close T: 42 daily sessions, at most 52 weekly bars, and at most 48 monthly bars. Some weekly/monthly histories are shorter and the page states the actual counts. Decide from visible price and volume *through T only*; no next-day result, ticker, date, candidate score, or source stratum is shown.

- **BOX:** a durable bounded range or gently drifting channel with repeated interaction around lower and upper zones. A brief undercut that recovers can still be BOX if the range remains intelligible.
- **NOT_BOX:** monotonic trend, persistent breakdown, or a noisy structure with no reasonably repeatable range. Lack of positive proof is not automatically NOT_BOX.
- **UNCERTAIN:** visible history is insufficient or the structure is genuinely transitional/ambiguous. It is a valid primary answer and should not be forced into a negative.

For BOX, choose current position LOWER/MIDDLE/UPPER/BREAKDOWN/UNCERTAIN. NOT_BOX permits BREAKDOWN or UNCERTAIN; UNCERTAIN shape requires UNCERTAIN position. Subtype is required to distinguish sideways range, drifting channel, noisy consolidation, monotonic trend, transient undercut and recovery, persistent breakdown, insufficient history, or undecidable. Reasons and short note are optional; confidence HIGH/MEDIUM/LOW is required. Do not infer confidence from future return.

## Optional coordinates

`Evidence begins` is the leftmost **daily** candle you regard as relevant, counted from 0 (oldest) to 41 (decision close T). The evidence interval always ends at 41. Leave it blank if a start is not defensible. `Lower boundary %` and `Upper boundary %` are approximate **percentage differences from T's daily closing price**, not absolute prices or screen pixels. Each chart's left edge has relative-percent reading aids. Enter both boundaries for BOX or leave both blank; lower must be below upper. NOT_BOX and UNCERTAIN have null boundaries. A reviewer may use UNCERTAIN when boundaries cannot be agreed on. These are human estimates, not LEAN orders, stop prices or trained targets.

## Workflow and provenance

Save creates a new immutable revision; reopening a saved task and saving again creates the next revision. Undo resets the unsaved form to the latest saved revision. Skip logs an event without making a label. Previous/Next navigate the blinded task order. A refresh reloads saved state from SQLite. Opaque task IDs are for storage only; repeated cases in a future pool must receive distinct opaque tasks with their mapping hidden from the page. Reviewers should judge repeats independently.

For an initial reliability pilot, label about **20–30** available cases and revisit a blind subset after a delay when a properly versioned repeat pool is available. The current 30-task batch contains no deliberate delayed repeat tasks. Within-rater agreement cannot be estimated from it yet. No assistant or heuristic should supply human labels. Ground Truth export and real-label model training are intentionally disabled in v1.1 pending a later work order.

## Limits before a larger pool

The v1 control draw was deterministic after a capped scan. It supplies neither full-universe inclusion probabilities nor a sound false-negative recall estimate. The P1 design requires verified issuer grouping and complete eligible denominators before generating a new 180-task pool. If those are missing, stop rather than silently treating ticker strings or surviving listings as issuer identity. Human pilot judgments on the existing batch are about ontology clarity only.

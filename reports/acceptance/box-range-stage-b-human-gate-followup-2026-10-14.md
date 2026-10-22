# Stage B human-label progress gate — 2026-10-14

The read-only `check_box_range_stage_b_human_gate.py` validates the frozen
selection, private detector audit, task manifest/receipt and every v1.1 human
annotation revision before reporting counts. It opens only the human SQLite
namespace. The separate smoke namespace cannot satisfy the gate. It computes
no detector quality metric and reads no future outcome.

On the live local 48-task batch, the result is **AWAITING_HUMAN: 0/48 labeled,
0 human revisions**. The selection and manifest SHA-256 values match the
original frozen receipts; see the aggregate [receipt](../evidence/box-range-stage-b-human-gate-2026-10-14.json).

Stage A/B focused regression after this addition: **31 passed**. A synthetic
isolation test saved a smoke annotation and confirmed progress stayed at zero,
then saved a separate fixture human revision and confirmed its provenance and
completion state. Deliberately corrupting the fixture's label version was
rejected. No annotation was written to the real human store by this test.

This gate is a progress and integrity check, not a substitute for genuine
blind judgments. Even 48/48 valid labels would leave the issuer-provenance
review and a version-frozen detector comparison to finish. The current Stage B
quality verdict remains pending.

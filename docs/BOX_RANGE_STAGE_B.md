# Box RangeDetector Stage B — local labeling and audit

The live private audit set is a pre-frozen 48-task Train/Validation draw. It
belongs to Stage B only; it does not replace the old 30-task Box-LQ1 pilot.
Selection, private ID/date mapping, charts, tensors, Alpaca history and label
databases stay under the ignored local `stock-radar/data/box-range-stage-b/`.

## Open the human page

The local Label Studio extension is available at
`http://localhost:8125/box-label/v1.1/human/` while its server runs. It uses
the existing Label Studio account. The page hides symbol, date, score and
detector judgment. It shows 42 daily candles, up to 52 weekly and up to 48
monthly. The headings give actual history lengths; for 2022 and some other
stocks the four-year panel is incomplete. `UNCERTAIN` is valid when evidence
cannot support a confident judgment.

Choose Structure, Current position, Subtype and Confidence; optional evidence
start, paired relative-percent boundaries, reasons and note can clarify a BOX.
Save advances to the next task. Previous/Next navigate; opening a saved task
and saving again creates an immutable revision. Refresh reloads saved answers.
Only the owner should provide substantive judgments. The `/smoke/` route is
for technical tests and must never be counted as human Ground Truth.

To check actual progress without exposing labels or producing detector quality
claims, run this read-only command from the Stage B worktree:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
..\stock-radar\.venv\Scripts\python.exe scripts\check_box_range_stage_b_human_gate.py `
  --selection '..\stock-radar\data\box-range-stage-b\blind-selection-v1.json' `
  --task-root '..\stock-radar\data\box-range-stage-b\blind-label-tasks-v2' `
  --detector-audit '..\stock-radar\data\box-range-stage-b\private-detector-audit-v1.json'
```

It verifies the frozen task mappings and every saved human revision. Smoke
annotations are never read. `LABEL_SET_COMPLETE_QUALITY_PENDING` means only
that all 48 tasks have valid saved labels; issuer review and a separately
versioned detector comparison are still required before a quality verdict.

If the service is stopped, start it from this worktree in PowerShell:

```powershell
& .\scripts\start_box_labeling.ps1 -Port 8125 `
  -ResearchRoot '..\stock-radar' `
  -BoxDataRoot '..\stock-radar\data\box-range-stage-b\blind-label-tasks-v2' `
  -CodeRoot (Get-Location).Path
```

## Reproduce in a new private directory

The existing selection and live task batch are immutable. The preparation CLI
will refuse to overwrite them. To repeat the protocol under a new versioned
private path, first `freeze` against frozen RI v1, record its SHA-256, then
`materialize` with that exact hash, run `verify_box_labeling.py`, and only then
run `audit_box_range_stage_b.py`. The detector audit refuses to overwrite its
own private result. This order prevents choosing the blind audit after seeing
detector judgments. Never copy private manifests, charts or annotations into
the Git repository diff.

The current aggregate checkpoint and limitations are in
`reports/acceptance/box-range-stage-b-2026-10-13.md`. The blind batch is
security-ID independent. The RI-recorded construction evidence provides one
as-of-T CIK per task and no CIK overlap with the earlier pools or six familiar
symbols, but all identities remain observational. The later
[as-of-T identity follow-up](../reports/acceptance/box-range-stage-b-identity-followup-2026-10-14.md)
found one incompatible-name evidence set by T and one only after T; the
all-time identity table flags both. Issuer separation is provisional until
provenance review is complete.
Do not compute an accuracy rate or advance the lower-band strategy until real
human structure labels and that identity gate are complete.

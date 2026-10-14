# Box daily context scan — Stage D

The scanner enumerates supported, research-ready 126-session security-days in
the **frozen Train or Validation split only**. It uses Research Infrastructure
v1's trusted `BoxHistory` prefix through decision close T, evaluates the
quantile and confirmed-pivot detectors independently, and then evaluates the
versioned lower-band context. No future price, label, return, or portfolio
state enters selection. Results are **research context**, not executable
orders or a completed signal stream.

Each date is divided into deterministic 256-security chunks. An immutable
private receipt contains the indexed/eligible denominator, source/basis,
processed/excluded counts, both detector state totals, and active context
rows. It is stored only beneath the local project's ignored `data` directory.
Existing chunks are checksum-, config-, code-, RI-, selection- and denominator-
checked before reuse, including the history reader, canonical OHLCV hasher and
Python/library versions. If a prior process left a `.partial` file, the script
fails closed; investigate that file before retrying. It never silently
overwrites an existing receipt.

From the Stage D worktree, a bounded run is:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
..\stock-radar\.venv\Scripts\python.exe -m scripts.scan_box_daily_stage_d `
  --research-root ..\stock-radar --split train `
  --start 2024-07-01 --end 2024-07-01 `
  --output-dir ..\stock-radar\data\box-range-stage-d\daily-scan-v4 `
  --max-new-chunks 1
```

Run the same command again to verify completed chunks and continue to the
next one. Omit `--max-new-chunks` to finish the selected interval. Change the
split and dates together when scanning Validation. Historical Test, Fresh and
cross-split ranges are rejected.

Verify aggregate coverage without printing private identities:

```powershell
..\stock-radar\.venv\Scripts\python.exe -m scripts.verify_box_daily_stage_d `
  --research-root ..\stock-radar --split train `
  --start 2024-07-01 --end 2024-07-01 `
  --output-dir ..\stock-radar\data\box-range-stage-d\daily-scan-v4
```

`complete=true` means every expected chunk for the requested interval exists
and the verifier reconciles all eligible rows and both detector counts. It
also rejects extra or partial chunk artifacts for a selected day. It
does **not** mean the whole Train/Validation history is complete, that issuer
identities are certified, that raw LEAN execution data are available, or that
the detector predicts returns. Before a complete historical run, use the
measured day-level runtime to plan the long scan and keep its private
artifacts outside Git.

The later [necessary-gate audit](../reports/acceptance/box-fast-gate-stage-d-2026-10-14.md)
checks only whether a row could reach the exact Stage C near-lower state.
It rejects 69.0% of one real Train day's eligible rows without dropping any
of its 96 full-scan near-lower cases. It does not recover the other detector
states, and it is not integrated into this full-state scanner.

The separate [candidate-only scanner](../reports/acceptance/box-candidate-scan-stage-d-2026-10-14.md)
keeps only near-lower contexts. Unknown prefixes still undergo full detector
evaluation. It accepts the same frozen split bounds and writes separate
private immutable receipts. One complete Train day matches the full-state
reference exactly; one Validation day has also been scanned, without a
full-state Validation comparator. To continue or verify one day:

```powershell
$env:PYTHONPATH = (Resolve-Path src).Path
..\stock-radar\.venv\Scripts\python.exe -m scripts.scan_box_near_lower_stage_d `
  --research-root ..\stock-radar --split validation `
  --start 2025-06-02 --end 2025-06-02 `
  --output-dir ..\stock-radar\data\box-range-stage-d\near-lower-candidate-v1 `
  --verify-only
```

Remove `--verify-only` to create missing chunks, and optionally set
`--max-new-chunks 1` to bound each invocation. The full-state scanner remains
necessary for any study of other box states. Neither path produces orders or
formal portfolio results.

A separate [candidate execution-metadata audit](../reports/acceptance/box-candidate-execution-metadata-2026-10-14.md)
reuses the existing split-bounded ten-session coverage checker on the two
verified candidate days. Its low same-source raw coverage is a data-readiness
observation, not a future-price or return study. No LEAN-ready subset is
certified by metadata alone.

The [candidate as-of-T issuer audit](../reports/acceptance/box-candidate-issuer-asof-t-2026-10-14.md)
reuses the frozen construction-source and episode/CIK evidence on the same
two days. It isolates known alias/conflict rows and preserves the distinction
between an observational absence of known conflict and official identity
certification. The private issuer/raw intersection is only a dependency
diagnostic, not a LEAN-ready population.

The [live Train prefix checkpoint](../reports/acceptance/box-candidate-train-prefix-2026-10-14.md)
verifies a continuous 207-session interval through 2022-06-28, including
all 560 expected candidate chunks. The background scan may have written later
private files by the time this dated receipt is read; only a new verifier
result can expand the verified interval. Keep this distinction when reporting
progress.

The [cross-period parity receipt](../reports/acceptance/box-candidate-cross-period-parity-2026-10-14.md)
compares candidate-only and complete full-state outputs on two Train dates
and one Validation date. All 470 observed near-lower context rows match
exactly. This validates those dated receipts only; the ongoing backfill and
unverified dates retain their own denominator and identity/data gates.

The later [Validation-start addendum](../reports/acceptance/box-candidate-validation-start-2026-10-14.md)
verifies a four-session prefix and compares the exact first Validation day
against a complete full-state reference. It is a separate dated receipt;
do not overwrite the earlier three-day parity result or infer that the whole
Validation split is finished.

The [later dual-prefix checkpoint](../reports/acceptance/box-candidate-dual-prefix-2026-10-14.md)
independently verifies 222/753 Train and 6/235 Validation sessions, with
655/655 and 44/44 candidate chunks present. This extends only the verified
coverage intervals; the background processes and formal data gates remain open.

The [cross-era gate audit](../reports/acceptance/box-candidate-cross-era-gates-2026-10-14.md)
adds complete 2022 Train and 2024 Validation reference-day issuer/raw-metadata
checks. It finds zero same-source raw candidate sessions in the 2022 sample,
despite limited raw rows elsewhere in the period. Continuous prefix verification
later reached 224/753 Train and 8/235 Validation sessions. These candidate
contexts still have no official identity or formal execution certificate.

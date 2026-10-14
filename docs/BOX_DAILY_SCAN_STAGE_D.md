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

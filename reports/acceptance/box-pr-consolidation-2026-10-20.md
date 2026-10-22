# Box PR consolidation — 2026-10-20

The owner chose one reviewable [draft PR #28](https://github.com/zhoushuming073-cell/stock-radar/pull/28) instead of the dependent PR #24 → #25 → #26 → #27 chain. The four former drafts were closed as superseded; their GitHub PR refs and local worktrees still retain the dated commits. This is a branch and review change, not a new research result.

## Reconciliation

- Base: local and remote `main` at `d95d12cf45a9808cd4e0eb5608cf1de8adbb9088`, after roadmap PR #23 and labeling-foundation PR #21 merged.
- Source: final Stage C/D branch `feature/box-range-lower-band-stage-c` at `9cbeefef53292d21111d5ec27fa75ea61f21669b`.
- Transfer: apply the complete binary tracked-file diff from that base to the source branch onto one fresh branch from `main`. The transfer changed 293 tracked files, with 20,760 insertions and 33 deletions before status-document corrections. No private database, chart, annotation, credential or ignored runtime file was transferred.
- Updated only current status text in `ACTIVE.md`, the canonical ledger and research guides to explain the single-draft review route. Dated historical acceptance reports remain intact.
- The former PRs remain as dated review records; the consolidated draft is the current implementation review surface.

## Verification

- `git diff --cached --check` and the subsequent working-tree diff check passed before the full regression.
- Full project pytest from the consolidated checkout with `STOCK_RADAR_TEST_LEAN=1`: **824 passed, 8 skipped, one existing third-party `websockets.legacy` deprecation warning**. This includes eligible Native LEAN regression fixtures, not a box LEAN portfolio backtest.
- Path audit of the 293 transferred tracked files found zero `data/` or obvious credential/key/secret paths.
- Final source-to-consolidated tree comparison found exactly five changed current-status/route documents and no changed source, test, config or dated evidence files. The remote consolidated branch resolved to the tested commit, and GitHub reported PR #28 open, draft, based on main and mergeable.
- After consolidation, the new branch's candidate scanner reverified the original private frozen file sets with `--verify-only` against the unchanged local Research Infrastructure v1 root. Train: **753/753 sessions, 4,167 verified chunks, 78,607 candidate contexts, zero missing/new chunks**, file-set SHA-256 `350aa4ab25e1af5ecd1b06350ef819a2b5107d89ca911f928b97ea86c2b769b6`. Validation: **235/235 sessions, 1,748 verified chunks, 33,226 contexts, zero missing/new chunks**, SHA-256 `80f7f641045051fd80cae446ba1ebad7ab2c78694d6c76e1260e4054a6b33c96`. Both hashes equal the pre-consolidation public aggregate acceptance. The verifier read no future outcomes and produced no formal signal stream.
- The commit has no configured GitHub Actions workflow runs or commit-status checks. The real local receipt recheck and full pytest above are the available execution evidence; a Code Review check reader returned a connection error and supplied no diagnostics.

## Open gates

The 988/988-session Train/Validation candidate scan and all source audits remain engineering evidence. Independent detector truth, exact historical class/issuer identity, same-source accepted execution prices/actions/factors, frozen executable signals/rules and a formal box LEAN run are still unverified. The owner's free-data route remains in force. No Test/Fresh, future outcome study, QC Cloud job, synthetic human label or return claim was added in this consolidation.

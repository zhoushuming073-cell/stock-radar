# Repository branch index

> Reviewed 2026-10-13. Branch retention is not implementation or merge approval.

## Working entry points

| Branch / PR | Role | Disposition |
| --- | --- | --- |
| `main` | Accepted repository baseline | Default reading entry |
| `docs/codex-box-shock-research-20261013` / [#23](https://github.com/zhoushuming073-cell/stock-radar/pull/23) | Four research briefs, consolidated roadmap and this branch index | Single documentation review entry; planning only |
| `feature/box-labeling-v1-20261011` / [#21](https://github.com/zhoushuming073-cell/stock-radar/pull/21) | Current box labeling engineering baseline | Retain draft; partial-scale mask repaired at `2a283af`; human-label quality and model efficacy remain untested |

## Retained research checkpoints

| Branch / PR | Why retained |
| --- | --- |
| `quant-guided-human-labeling-v1` / #7 | Unmerged v1 historical implementation; #9 selectively reused components, not proof of full branch equivalence |
| `feature/parallel-channel-scanner-v1-20261009` / #10 | Original Q2 experiment; prior disposition keeps it until an accepted replacement merges |
| `feature/q1-q2-daily-lean-20261009` / #13 | Frozen Q1 execution blockers and Q2 evidence; base for #15 |
| `feature/q2-v1.2-high-beta-liquid-channel` / #15 | Unmerged v1.2 research; base for #16 |
| `feature/q2-v12-qc-exploratory` / #16 | Historical local proxy and Cloud incident evidence; Cloud remains stopped |
| `feature/q2-v13-relaxed-channel-plugin-20261010` / #20 | Unmerged user-run plugin checkpoint; local checkout also has later commits, so no reset |

These six older research branches are parked checkpoints, not six concurrent development tasks. Their unique deltas or stacked dependencies prevent treating them as garbage. Preserve private-data worktrees and local backup refs.

## Documentation consolidation receipt

The cleanup targets are:

- `codex/q2-v13-relaxed-plugin-workorder-20261010`
- `docs/quant-vision-cascade-idea-20261010`
- `docs/research-database-scorecard-20261010`
- `docs/sync-oct11-reports-index`

All four tips are ancestors of `origin/main` at review; remove their remote branch refs after a final ancestry/remote-head check. Their commits and documents remain in main.

`docs/box-range-structure-codex-prompt-20261013` contains one added design document. Its exact Git blob is preserved in #23; after #23 is pushed and verified, close #22 as consolidated and remove the redundant remote branch. This is **not** a claim that #22 or #23 was merged into main.

**Completed 2026-10-13:** all five listed remote branches were deleted after matching their live heads to the reviewed SHAs. GitHub API enumeration confirmed **14 → 9** remaining branches (main, one documentation branch, seven experimental code branches). PR #22 is closed as consolidated; PR #23 remains open and unmerged. HTTPS Git transport temporarily failed, so authenticated GitHub REST ref deletion was used. No experimental code merge or force overwrite occurred.

## Future branch rule

Use one implementation branch for the active bounded work order. Develop dependent box fixes from the explicit #21 head until the dependency is accepted. Put new research ideas in the proposal index; a new idea does not require another implementation branch. Remove merged documentation branches after preservation checks. Archive unique code only through a deliberate closure decision with a durable commit/tag and PR record.

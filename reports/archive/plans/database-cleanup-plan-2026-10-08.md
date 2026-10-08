# Database cleanup plan — 2026-10-08

Baseline: `168368de255501de6b45237037f52c3eaa1ea582`. Inventory before mutation: 22032 assets.

Only exact unreferenced, unpublished construction outputs are deletion candidates. Published stores, current source locks, raw evidence, runs, owner uploads and all tracked reports stay. Previously blocked Shape paths will not be retried.

| Asset | Class | Action | Bytes | Reason |
| --- | --- | --- | ---: | --- |
| `data/pit/construction/versions/32b31d12b438e36f8ac6c011c30b71e4d0031020f94cb9f75cedc87fa2f9b84c/historical.duckdb` | E | DELETE_CANDIDATE | 360984576 | Unpublished failed construction output; no manifest, no exact consumer, inputs preserved |
| `data/pit/construction/versions/924c3baf08c52747255ffe26d76ecb304e24b45219d3a1a74873e5df14d9b2c5/historical.duckdb` | E | DELETE_CANDIDATE | 721956864 | Unpublished failed construction output; no manifest, no exact consumer, inputs preserved |
| `data/pit/construction/versions/bc2c80335de6ebbc19e9eb6fc78b0499b751ecd97afe5fdec051b3c51b1b97ac/dividends.json` | E | DELETE_CANDIDATE | 4110839 | Unpublished failed construction output; no manifest, no exact consumer, inputs preserved |
| `data/pit/construction/versions/bc2c80335de6ebbc19e9eb6fc78b0499b751ecd97afe5fdec051b3c51b1b97ac/historical.duckdb` | E | DELETE_CANDIDATE | 988295168 | Unpublished failed construction output; no manifest, no exact consumer, inputs preserved |
| `data/pit/construction/versions/bc2c80335de6ebbc19e9eb6fc78b0499b751ecd97afe5fdec051b3c51b1b97ac/rules.json` | E | DELETE_CANDIDATE | 1243 | Unpublished failed construction output; no manifest, no exact consumer, inputs preserved |
| `data/pit/shape-research/versions/25137ad2123ffc57cc7873dcd0dab5307152e61f036d39b12900b4c3315c507e/manifest.json` | C | ARCHIVE_CANDIDATE | 5211 | Superseded local published Shape snapshot; keep manifest/hash and cold copy for investigation |
| `data/pit/shape-research/versions/7414e7f0e59204b92bf368b7ac2b989405b7095a6c03b3480688b14c75b3d348/shape.duckdb` | E | POLICY_BLOCKED_KEEP | 268185600 | Prior blocked deletion scope; do not retry or bypass approval policy |
| `data/pit/shape-research/versions/e1d74eb75b90412a4756748e3a1300f674c2add72a2d7a2ec7d5f86d0f3b6671/shape.duckdb` | E | POLICY_BLOCKED_KEEP | 3622055936 | Prior blocked deletion scope; do not retry or bypass approval policy |
| `data/pit/shape-research/versions/e1d74eb75b90412a4756748e3a1300f674c2add72a2d7a2ec7d5f86d0f3b6671/shape.duckdb.wal` | E | POLICY_BLOCKED_KEEP | 6969158 | Prior blocked deletion scope; do not retry or bypass approval policy |
| `data/pit/shape-research/versions/e1d74eb75b90412a4756748e3a1300f674c2add72a2d7a2ec7d5f86d0f3b6671/shape.duckdb.tmp/duckdb_temp_storage_DEFAULT-0.tmp` | D | POLICY_BLOCKED_KEEP | 1048576000 | Prior blocked deletion scope; do not retry or bypass approval policy |
| `data/pit/shape-research/versions/e1d74eb75b90412a4756748e3a1300f674c2add72a2d7a2ec7d5f86d0f3b6671/shape.duckdb.tmp/duckdb_temp_storage_DEFAULT-1.tmp` | D | POLICY_BLOCKED_KEEP | 1242562560 | Prior blocked deletion scope; do not retry or bypass approval policy |
| `data/pit/shape-research/versions/e1d74eb75b90412a4756748e3a1300f674c2add72a2d7a2ec7d5f86d0f3b6671/shape.duckdb.tmp/duckdb_temp_storage_S32K-0.tmp` | D | POLICY_BLOCKED_KEEP | 131072000 | Prior blocked deletion scope; do not retry or bypass approval policy |
| `data/pit/shape-research/versions/e1d74eb75b90412a4756748e3a1300f674c2add72a2d7a2ec7d5f86d0f3b6671/shape.duckdb.tmp/duckdb_temp_storage_S64K-0.tmp` | D | POLICY_BLOCKED_KEEP | 136052736 | Prior blocked deletion scope; do not retry or bypass approval policy |
| `data/pit/shape-research/versions/e1d74eb75b90412a4756748e3a1300f674c2add72a2d7a2ec7d5f86d0f3b6671/shape.duckdb.tmp/duckdb_temp_storage_S96K-0.tmp` | D | POLICY_BLOCKED_KEEP | 393216000 | Prior blocked deletion scope; do not retry or bypass approval policy |
| `data/pit/shape-research/versions/e1d74eb75b90412a4756748e3a1300f674c2add72a2d7a2ec7d5f86d0f3b6671/shape.duckdb.tmp/duckdb_temp_storage_S96K-1.tmp` | D | POLICY_BLOCKED_KEEP | 129859584 | Prior blocked deletion scope; do not retry or bypass approval policy |

Dynamic/basename-only references are REVIEW_KEEP. Existing PIT audit scripts remain explicit commands outside runtime, because tests, code locks or report reproduction reference them. Raw directories already constitute cold storage; moving locked raw paths would damage reproducibility.

No automatic table/view drop, tracked evidence deletion or all-market data expansion. File-level actions require the recorded pre-hash, exact workspace containment, no published manifest and no live pointer. Results recorded separately.

## Action review

The first audited exact-file delete was blocked by policy; all five failed construction files will be retained and recorded, without retry via another tool. The published obsolete Shape version is classified as a whole cold archive: three files, own-manifest references only, no external consumer. No active or frozen evidence path is moved.

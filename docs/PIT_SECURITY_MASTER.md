# Historical security master import

Stock Radar starts in `current_snapshot` mode. Historical results in that mode
have **Survivorship Bias Risk: Present** because the observed asset snapshot
does not reconstruct every historical listing, delisting, or ticker change.

The optional `point_in_time` mode reads three local, untracked files:

```text
data/security-master.csv
data/security-master-manifest.json
data/security-master-feature-store.json
```

CSV columns:

| Column | Meaning |
| --- | --- |
| `security_id` | Stable security identity across ticker changes; never reuse it for another security. |
| `symbol` | Symbol valid in the inclusive `valid_from` / `valid_to` interval. |
| `valid_from`, `valid_to` | First and last date of this symbol mapping; blank `valid_to` means open ended. |
| `listing_date`, `delisting_date` | Actual exchange events; blank means unknown. Observation boundaries are not listing/delisting dates. |
| `exchange`, `security_type` | Historical market classification. |
| `eligible` | `true` / `false` membership flag for this mapping. |
| `security_name` | Optional name valid for this interval; otherwise the symbol is displayed. |

Example structure (synthetic, **not actual market history**):

```csv
security_id,symbol,valid_from,valid_to,listing_date,delisting_date,exchange,security_type,eligible
EXAMPLE-1,OLD,2020-01-01,2021-06-30,2020-01-01,,NYSE,common,true
EXAMPLE-1,NEW,2021-07-01,,2020-01-01,,NYSE,common,true
```

Manifest structure:

```json
{
  "provider": "Actual licensed source name",
  "source_version": "Source snapshot ID or date",
  "coverage_start": "2020-01-01",
  "coverage_end": "2026-09-25",
  "coverage_complete": true
}
```

`coverage_complete` is a statement by the importer about the source data. Set
it only after checking source documentation, membership completeness,
corporate-action/ticker mapping quality, and the requested US-equity market.
The adapter verifies required fields, overlapping symbol/identity mappings,
nonempty daily membership, requested-date bounds, and source fingerprint. These
checks **cannot prove** that a vendor's historical universe is complete.
The repository now ships an open-source snapshot importer. Large raw snapshots,
normalized masters and feature databases remain local under ignored `data/pit/`.
Its first reconstruction is exploratory, with `coverage_complete: false`,
`source_attested_completeness: false`, `reconstruction_kind: snapshot-interval-v1`,
explicit `coverage_windows` and an exact `output_sha256`. The adapter rejects
unknown reconstruction kinds, changed output bytes and dates within source gaps.
It must not be presented as a certified unbiased historical universe.

PIT Scanner filters candidates and its same-date base-rate population through
the dated security master. Forward labels follow `security_id`, so a ticker
change can retain identity and ticker reuse cannot inherit another security's
future bars. PIT Backtest filters the same dated membership and fails safely if
an open position loses a required price mark; it does not fabricate a final
delisting close. Runs store mode, provider, source version, coverage, and file
fingerprint. Changing the imported files after a run is queued fails that run.

Price history, feature history, and corporate-action-adjusted series must also
cover delisted securities. A security master alone does not fill missing bars.
LEAN remains the formal execution engine; **PIT LEAN execution remains rejected**
until corporate actions, identity maps and terminal economics are trustworthy.

## Reconstruction sources and uncertainty

The primary source is historical Git commits in
[rreichel3/US-Stock-Symbols](https://github.com/rreichel3/US-Stock-Symbols),
including the predecessor before the requested start. Its workflow actually
calls the **NASDAQ Screener API**, filtered to NASDAQ/NYSE/AMEX, at midnight UTC.
This is not the exhaustive official NASDAQ Trader Symbol Directory. Commits
at/after 16:00 America/New_York become usable on the next calendar date for daily
close scanning. Availability timestamps and raw file hashes are retained.

Snapshots become intervals with at most four calendar days of carry by default.
Empty/invalid/duplicate/missing-exchange observations and total-count changes
over 15% are rejected. Known failures stop carry; source gaps fail queries.
Smaller screener omissions can remain undetected. Disappearance ends an observed
membership episode, not a confirmed delisting. Reappearance or an unverified
issuer-name change creates a separate unresolved episode. Episode counts are
not counts of verified securities.

[YLiu95/delisted-equity-data](https://github.com/YLiu95/delisted-equity-data)
supplies secondary delisting/reuse claims;
[Quant-Lodge/ticker-reference-data](https://github.com/Quant-Lodge/ticker-reference-data)
supplies undated rename/CIK candidates. Neither automatically merges identities.
SEC bulk retrieval returned HTTP 403 on this machine. Dated official SEC and
NASDAQ notices establish FB→META Class A, effective 2022-06-09, through the small
reviewed `config/pit_identity_evidence.json`. Mappings are scoped to issuer/class
names and dated boundaries. Corrections to nearby lagging observations are
audited. CIK alone is issuer identity and cannot identify every share class.

No LICENSE/COPYING file was found in the three pinned source trees. Public
availability does not establish redistribution permission; raw/normalized data
and detailed symbol exports remain local. Only code, tests, evidence references
and aggregate reports are committed.

## Instrument and identity policy

Native instrument/test flags take priority when available. The primary screener
lacks reliable native instrument flags, so explicit instrument descriptions
produce **inferred** types; an unclassified name becomes `unknown`, never common
by default. Blank-check industry is SPAC. Types distinguish common, ETF, ETN,
preferred, warrant, unit, rights, closed-end fund, ADR, SPAC, test and other/unknown.
Default eligible type is `common` only; all other types remain in the observed
master/coverage report but are ineligible. Description-based common-stock
inference remains fallible, including structured/fund products. Official
historical instrument enrichment is still required.

Additional CSV fields retain identity/type status, resolution method, evidence
URL, first/last source commit and observation dates. `snapshot-audit.json`
contains accepted/rejected observations, file hashes, missing dates, gaps and
identity corrections. Unresolved observations use conservative episode IDs;
verified dated evidence can join rename intervals into a stable security ID.

## Offline replay, features and installation

Run from the repository with the project environment. Network access is explicit:

```powershell
.venv/Scripts/python.exe -B scripts/build_pit_universe.py --download --end 2026-10-07 --identity-evidence config/pit_identity_evidence.json
# Substitute the printed version for <version> below.
.venv/Scripts/python.exe -B scripts/build_pit_features.py --build data/pit/normalized/<version>
.venv/Scripts/python.exe -B scripts/audit_pit_universe.py --build data/pit/normalized/<version>
.venv/Scripts/python.exe -B scripts/compare_pit_scanner.py --build data/pit/normalized/<version>
.venv/Scripts/python.exe -B scripts/build_pit_universe.py --end 2026-10-07 --identity-evidence config/pit_identity_evidence.json --lock data/pit/normalized/<version>/source-lock.json --install
```

`--download --update` explicitly fetches upstream changes; omit both for offline
replay. Preserve the start/end, stale-day policy, evidence file and source code
revision. Build version binds source commits, importer version/source hashes,
evidence, policy and output CSV hash; the original Stock Radar code baseline is
recorded separately in metadata. Build timestamp
is metadata outside version identity. Changed output cannot replace an existing
version. Installation refuses existing root inputs; review a new version in its
own directory before separately managing promotion.

Feature construction creates a **new** `pit-research.duckdb` without replacing
old databases. It uses unchanged causal formulas/configuration, resets rolling
history at unresolved identity boundaries and preserves verified rename history.
Missing bars stay missing; labels are not precomputed. The feature sidecar binds
master CSV, source research database, research config, feature database and
builder hashes. **Every PIT import**, including older certified masters, needs a
compatible sidecar before Scanner use. Old symbol-only survivor features are
rejected. Moving a store requires a reviewed sidecar path update and changes its
fingerprint.

`LocalSecurityMaster.observed_on(date)` exposes all observed instruments;
`eligible_on(date)` supplies the research population. `filter_frame` maps by
symbol/date and rejects a mismatched existing `security_id`. Both the loader and
production Scanner enforce dated membership. Runs bind version/fingerprint and
feature provenance; loaders also verify source/feature database bytes.

These controls do not prove that supplier raw-symbol bars belong to the asserted
historical instrument. Vendor identity cross-checks remain required. Queue and
worker bound label horizons and actual price/session reads to the frozen
evaluation end. Batch variants share one captured research snapshot and fail
atomically on source mutation. Consuming Backtests preserve and validate the
signal-producing Scanner implementation provenance.

Coverage audits keep no-price instruments in the denominator and distinguish
all observed episodes from eligible common episodes. A secondary delisting-price
proximity audit is explicitly unverified; it cannot establish terminal value.
The frozen-strategy comparison examines historical selection only, without
future returns. See [architecture audit](../reports/pit-initial-audit-2026-10-07.md)
and [local acceptance](../reports/pit-acceptance-2026-10-07.md).

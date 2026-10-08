# Reusable historical database

This database is independent of any strategy, Core ranking, Native Run, or QC
export. It preserves the installed master IDs and does not overwrite the root
master, features, accepted prices, formal gates, or strategy rules.

## Build and audit

Run from the repository with its Python environment. The existing normalized
master and research source stores are prerequisites, not downloaded by these
commands. New reference Git caches must exist under
`data/pit/raw/database-construction/{cik-history,nasdaq-history}.git`.

```powershell
.\.venv\Scripts\python.exe -B scripts/acquire_pit_database_references.py --end 2026-10-07
.\.venv\Scripts\python.exe -B scripts/build_pit_database.py
.\.venv\Scripts\python.exe -B scripts/apply_pit_database_review.py reports/evidence/pit-database-ttgt-review-2026-10-08.json --raw-dir data/pit/raw/database-construction
.\.venv\Scripts\python.exe -B scripts/supplement_pit_database_prices.py --security-id SEC-0000886158-COMMON --symbol BBBY --start 2021-09-01 --end 2023-05-02 --asof 2023-05-02
.\.venv\Scripts\python.exe -B scripts/audit_pit_database.py
```

The builder pins input bytes and code, checks raw reference hashes, validates
identity intervals, rejects malformed/mixed accepted prices, and checks all
inputs again before publishing. `data/pit/construction/current.json` selects a
content-addressed version with `historical.duckdb` and `manifest.json`.
Unfinished builds have no manifest and are not published. Audit output includes
`scorecard.json`, `daily-scorecard.csv`, and `survivorship-sample.json`.

The manifest is portable metadata only when its referenced local artifacts are
also available. All raw data and databases stay ignored/local. The public
report contains aggregate measurements and source hashes, not redistributed
directory/market exports.

## Query contract

```python
import json
from pathlib import Path
from radar.pit.database import HistoricalDatabase

pointer = json.loads(Path("data/pit/construction/current.json").read_text(encoding="utf-8"))
with HistoricalDatabase(Path(pointer["directory"])) as history:
    observed = history.population_on("2024-09-30")
    unknown_absences = history.uncertainty_on("2024-09-30")
    candidates = history.candidate_population_on("2024-09-30")
    # Keep uncertainty alongside observed members when studying universe bias.
    # Do not use the full-window identity_quality table to select past stocks.
    bars = history.prices("SEC-0000718877-COMMON", "2023-01-01", "2023-10-12")
```

`population_on` returns the **observed** historical candidate population. It
keeps common, ADR, warrant, unit, and unknown-class records separate. Its four
states are confirmed member, probable member, unknown, confirmed nonmember.
The `member` column uses nullable Boolean values; unknown is `pd.NA`.
`membership_on` returns unknown for an absent/unobserved identity unless a
documented listing or cessation establishes a boundary.

`uncertainty_on` exposes previously observed IDs whose observation ended
without verified cessation. This includes possible fragmented identities. It
does not claim they are still listed. Future first observations are not
backfilled. `candidate_population_on` combines both sets; a strategy must bound
the effect of unknown competitors rather than treat them as false. The size of
this union is **not** an estimate of the actual US listed market.

`eligible_on` is source mapping eligibility for the observed population. It is
compatible in ID/date scope with `LocalSecurityMaster.eligible_on`; unknown
absences remain available through the separate uncertainty API. Existing
`load_universe` and formal execution policies are unchanged. This explicit
adapter is not automatically promoted as the formal master.

`filter_frame` requires explicit `security_id`, historical `symbol`, and `date`.
It returns membership/type/exchange metadata without applying future A/B/C
ratings. It rejects mismatched intervals, issuer conflicts already known by
that session, and installed identity-discontinuity quarantines. It supports
existing PIT features and raw-price rows; missing features stay missing.

`prices` exposes the independently accepted **raw** series only. Every row has
source, fixed source version, retrieval timestamp, date-specific ticker, ID,
basis, action relation, conflict state and source-database hash. There is no
fallback to legacy split-adjusted bars. The latter are stored only as bounded
availability/provenance observations, not spliced into the raw series.

The price supplement checks a missing series against **verified** historical
identity intervals before requesting data. A dated Alpaca `asof` selects the
historical entity; the provider's default current-date entity is not used.
Raw SIP responses and SPY/QQQ benchmarks are hash-cached separately, with
pagination checked. The resulting child version contains new raw prices and
`supplemental_features` using the existing feature schema/formulas/config.
Cross-sectional scores remain NULL; source/terminal economics remain separate.
The installer refuses an existing series to prevent implicit splicing. Apply
the ordered build/review/supplement sequence once; further changes start from
a selected immutable parent rather than blindly reapplying the same review.

## Evidence and membership

`security_episode` represents each continuous lifetime within a retained
internal ID. `ticker_episode` preserves its exact symbol/type/exchange intervals.
Issuer CIK evidence is a candidate relationship, not proof of a share class.
Class descriptors from source names are distinguished from reviewed official
class identities. Unknown predecessor/successor remains NULL.

`evidence_graph` connects issuer → security → class description → ticker episode
→ exchange interval → price series, plus lifecycle edges. Every edge carries
source/version, hash, dates, confidence, and a known-on date or explicit NULL.
Evidence IDs resolve to dated, pinned raw Git snapshots. A/B/C is a full-window
audit only. No automatic identity splice uses CIK, a ticker, or a similar name.

Primary observation freshness is four calendar days; secondary freshness is
31 days. Only secondary observations available by the session can corroborate
it. Git committer dates use the existing New York close cutoff. They are mirror
availability dates, not the upstream announcement dates. SEC issuer registry
and Nasdaq common-stock descriptions corroborate membership within the
observed census. Nasdaq-derived sources can share an origin; two mirrors do
not establish independently attested full-market completeness. Stale or absent
secondary evidence leaves probable membership; disagreement or a known CIK
collision leaves unknown. Test/ETF fields absent in a mirror are not assumed
false; explicit common/ordinary descriptions are required for Nasdaq support.

The observed session calendar comes from installed SPY bars and is hash-bound.
It is not an independent exchange holiday attestation. No data before
2021-09-01 or outside the manifest/session calendar is claimed.

## Review installation and lifecycle

`identity_lifecycle_review_queue` groups reason, interval, source hash, class
scope, severity, and status. Common-stock priorities are separate from tens of
thousands of other-class fragments. Detectors cover reuse, multiple CIKs,
class/issuer/name/exchange transitions, observed beginnings/endings, raw-price
jumps, zero volume, long gaps, extreme volume and cross-source price conflict.
Triggers are questions, not legal delistings or adjustment instructions.

`lifecycle_event` supports split/reverse split, ticker/exchange transfer,
merger/acquisition/cash acquisition/stock conversion, bankruptcy, delisting,
OTC continuation, suspension, termination and class transitions. A supported
type with no sourced records is not a claim of coverage. Ordinary dividends
are separate (`cash_dividend` and source JSON). Terminal cash/stock economics
remain disabled until the independent settlement model is verified.

Machine-readable review packets must validate schema, interval scope, HTTPS
source/version, publication/retrieval chronology, actual raw hash and excerpt,
and interval nonoverlap. The annotation installer copies the parent into a new
hash-bound version; identities, mappings and price histories cannot be merged
through this channel. Conservative quality quarantine starts no earlier than
both its disputed boundary and source publication. Feature/price consumers
then reject an unresolved identity discontinuity. The parent is retained for
rollback. Accepted identity fact changes require the existing trust-catalog
validator/master rebuild workflow and independently sourced security-class
facts; AI text cannot perform them.

## Scorecard interpretation

`config/pit_database_rules.json` fixes broad database criteria independently
of strategy gates. Percentages separately describe common candidate IDs,
observed common member-days, detected common lifecycle records, and sampled
cases. Prior-observation uncertainty outside the observed census is reported
in replay separately. These denominators are not interchangeable and do not
measure complete-US coverage. There is no fabricated average completion score.

The seeded audit selects 50 per eligible stratum without hand-picking. Verified
exchange-listed cessation includes documented suspension/completed M&A, with
legal delisting effect and OTC continuation separately unresolved. Cessation,
confirmed rename and M&A shortfalls are disclosed; suspicious
disappearance does not fill them. A retention pass alone is insufficient for
research completeness: prices, features, identity and event handling are
measured independently. Tier 2 and maintenance require the stated evidence
thresholds, not just that the framework or a particular Run works.

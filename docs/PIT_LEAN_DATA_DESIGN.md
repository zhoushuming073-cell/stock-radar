# PIT execution contracts and remaining formal data blockers

Stock Radar generates its own **Stock Radar generated PIT execution dataset**.
It is not QuantConnect official Security Master data. Global completeness and
run readiness are separate. The installed reconstructed population remains
incomplete; formal portfolio status is documented in the
[final acceptance](../reports/pit-final-acceptance-2026-10-07.md) and latest
[data clearance](../reports/pit-clearance-acceptance-2026-10-07.md).

The installed IREN identity correction removes its independent map-root collision.
The full frozen Validation still has 435,678 missing prices and 6,416 unresolved
identities. Native execution remains blocked; 397 passing tests are engineering
evidence, not a completed formal PIT portfolio.

The scoped membership policy `pit-formal-membership-v1` requires the full dated
population hash, frozen source evidence, an official completeness declaration or
independent origins, and seven explained checks: continuity, exchange coverage,
carry, anomalies, future listing exclusion, disappeared securities and class
boundaries. It does not require global perfection. Current sources cannot attest
this Run's population completeness.

`no_material_action_review` requires complete identity-bound source coverage of
all material event types over every required session. Empty event results cannot
certify absence. Resolution price acquisition now requests only missing sessions
inside reviewed mappings and skips complete price scopes. `merge_price_gaps`
audits exact raw gaps, source/identity/license locks and rejects source overlap;
it does not implicitly convert or install the legacy split-adjusted broker data.

`scripts/audit_pit_formal_blockers.py` builds an inventory from the full formal
dependency closure; `--frozen` replays and verifies an existing locked closure.
`scripts/probe_pit_formal_sources.py` records bulk source discovery in quarantine.
Source availability and CIK candidates are not acceptance certificates.

## Frozen dependency closure

`radar.pit.run` includes every eligible historical member on every signal date,
all actual feature/rank participants, selected signals, 126-session causal stock
warm-up, potential next-open/maximum-hold/exit lifetimes, mapping, actions,
terminals, SPY/QQQ history and calendar. Unpriced members stay in the denominator.
A rejected market day does not authorize removing Scanner population dependencies.
A selected-only whitelist cannot certify a full Strategy 2 Run.

The content-addressed manifest binds strategy/config/version, source Scanner,
all IDs and dates, required/missing prices, logical row hashes, physical master,
sidecar, feature/source/external DBs, reviews, license and original query/official
bytes. Acquisition/build clocks remain receipts. Queue and worker verify these
locks; execution rechecks after native completion. Mutations fail; PIT never
falls back to Current Snapshot.

`run_pit_readiness` has six preflight gates: Identity, Membership, Price,
CorporateAction, Terminal, LEAN Input. Every gate must PASS before native startup.
LEAN Native Execution and Result Reconciliation remain NOT_RUN until successful
native completion/reconciliation. Global unresolved intervals outside this Run
are not a veto. Required population completeness, class/issuer/exchange/rename
and price/action evidence inside the Run remain mandatory source-dependent claims.
No broad `ready=true` flag substitutes for scoped, hash-bound evidence.

New queued PIT attempts preserve both global and run scorecards in Run History.
A blocked attempt becomes failed with a specific BLOCKED error before LEAN is
invoked. This persists the attempted Run ID without calling it a completed
portfolio. Current Snapshot retains its original execution assumptions.

## Resolution factory

`radar.pit.resolution` uses an atomic SQLite lease queue, immutable dependency
keys, P0 unresolved Run dependencies, P1 selected/near-threshold dependencies,
bounded workers and retained attempt decisions. Repeated seeding is idempotent;
expired leases resume. Failed worker attempts can retry at most three times.
The official SEC current metadata table is discovery only; it cannot certify
historical class, listing or ticker reuse. Access denials are not bypassed.

Workers reuse scoped local official evidence. Verified mappings can fetch pinned
public OHLCV/split/dividend/symbol payloads, then quarantine them. A separately
reviewed exact-session acceptance declaration can produce a new accepted store;
replay revalidates raw/license/row hashes without overwriting it. Installation,
feature generation and full Run certification remain separate steps. Unknown
names never merge; absent license, missing sessions and unknown basis never pass.

```powershell
.venv/Scripts/python.exe -B scripts/run_pit_acceptance.py
.venv/Scripts/python.exe -B scripts/resolve_pit_run.py --dependency <frozen-manifest.json> --queue data/pit/resolution.sqlite3 --limit 20
.venv/Scripts/python.exe -B scripts/resolve_pit_run.py --dependency <frozen-manifest.json> --queue data/pit/resolution.sqlite3 --limit 20 --network --price-pin vt6qeesk27k07492k5jc5b7p04mf0s6o
```

Raw data, acceptance stores, queues and native bundles stay ignored/local. Public
SQL uses immutable AS OF, small date lists, hash-verified caches, transient-error
retries/Retry-After and explicit failed/truncated/invalid-payload quarantine.

## Maps, factors and price basis

Native source is pinned at `82810ea63d5542f05dc58f9d1db0557cf174d0ea`.
Map rows use interval **end** dates; `HasData` additionally uses first/final dates.
The first generated map date is frozen research input coverage, not an asserted
IPO. Root ticker reuse collisions remain blocked until a SID alias adapter is
validated. Exchange transfer keeps identity on the supported US route.

Raw execution prices and causal split-only feature prices are distinct.
`causal_identity_features` recomputes the original feature formulas at each known
split boundary, rescaling past OHLC and reciprocal volume only for subsequent
feature rows. A future split cannot change earlier feature rows. Raw source bars
stay raw in the database. Supplying an already split-adjusted store to the raw
builder is rejected. Dividend-adjusted inputs are not raw execution inputs.

Factor changes use the real preceding trading session and raw reference close.
A pre-research factor seed is necessary for LEAN's minimum-data-date parser.
Native RAW mode adjusts holdings once. The adapter updates fill annotations,
not holdings a second time. Reverse-split fractional shares use native cash in
lieu; that cash is separately reconciled to fills and the native cash balance.
Reviewed raw public acceptance can use `--raw-actions`; the bound feature build
uses the same reviewed ledger. Current Snapshot calculations are unchanged.

`corporate_action_event` stores identity/type/date/symbols/ratio/consideration,
source/hash/version/confidence, handling mode and full evidence. Missing records
never attest no events. General dividend factors/cash and stock-merger conversion
remain unsupported and block affected lifetimes.

## Terminal economics

Only explicit reviewed ordinary-common cash entitlement is supported. The official
ATVI 8-K states conversion into the $95 cash right at merger effective time. The
PIT convention recognizes that gross USD right at the reviewed effective date,
with declared zero settlement fee; it does not claim actual bank payment date,
investor withholding, appraisal elections or special treasury/parent-share terms.
The settlement updates LEAN's native cash book and native holdings, with before/
after reconciliation. It is a corporate-action settlement, not a market fill,
last-close substitution, synthetic quote or broker trading order.

For this convention the native map end is economic lifecycle end, after cash
recognition; last tradable session is independently enforced by the price ledger.
It is not labeled legal delisting. Ending the map at the last quote would let
LEAN automatically liquidate at that quote instead of the disclosed entitlement;
real/synthetic native tests witness this boundary. No post-cessation bars are made.

Bankruptcy/uncertain recovery, OTC continuation and unknown payout stay BLOCKED;
they never become zero. Rename preserves identity and is not terminal. Stock
mergers remain blocked even when a secondary scalar/ratio is available.

## Native evidence and interpretation

Real FB/META rename, NVDA 10:1 split and ATVI $95 entitlement accounting witnesses
run through native LEAN and normalized equity/cash/fee/order reconciliation.
Their signals are hand-authored accounting tests, not full Strategy 2 Scanner
portfolios. Dolt META misses June 9/10 2022 and is quarantined for that interval;
the rename witness uses the original local broker snapshot with residual vendor
identity risk explicitly preserved. A few passing cases do not certify the Run.

Normalized trade counts include economic entitlement closures; LEAN TradeBuilder
broker-order counts need not equal these counts. Native equity, cash, fees and
actual fill orders must reconcile. Existing raw/normalized results remain local.
Historical Validation/Test results remain retrospective, never Fresh OOS.

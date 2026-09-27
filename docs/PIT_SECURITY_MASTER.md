# Historical security master import

Stock Radar starts in `current_snapshot` mode. Historical results in that mode
have **Survivorship Bias Risk: Present** because the observed asset snapshot
does not reconstruct every historical listing, delisting, or ticker change.

The optional `point_in_time` mode reads two local, untracked files:

```text
data/security-master.csv
data/security-master-manifest.json
```

CSV columns:

| Column | Meaning |
| --- | --- |
| `security_id` | Stable security identity across ticker changes; never reuse it for another security. |
| `symbol` | Symbol valid in the inclusive `valid_from` / `valid_to` interval. |
| `valid_from`, `valid_to` | First and last date of this symbol mapping; blank `valid_to` means open ended. |
| `listing_date`, `delisting_date` | Actual exchange listing interval; blanks are allowed when source certifies coverage. |
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
No real PIT data or vendor adapter ships with this repository.

PIT Scanner filters candidates and its same-date base-rate population through
the dated security master. Forward labels follow `security_id`, so a ticker
change can retain identity and ticker reuse cannot inherit another security's
future bars. PIT Backtest filters the same dated membership and fails safely if
an open position loses a required price mark; it does not fabricate a final
delisting close. Runs store mode, provider, source version, coverage, and file
fingerprint. Changing the imported files after a run is queued fails that run.

Price history, feature history, and corporate-action-adjusted series must also
cover delisted securities. A security master alone does not fill missing bars
and is not a guarantee of unbiased research.

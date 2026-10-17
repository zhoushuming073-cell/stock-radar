# Box candidate official-evidence inventory — 2026-10-16

**Result: formal as-of-T identity and LEAN execution readiness remain unverified.** This is a read-only, aggregate inventory of the frozen historical construction database, not a new candidate filter or an identity adjudication. The actual database SHA-256 was checked against the pinned construction manifest before querying. No security/date mappings, prices, future outcomes, or private records are published.

| Frozen construction database inventory | Count |
| --- | ---: |
| Verified lifecycle events / security IDs | 15 / 9 |
| Verified lifecycle events with `known_on` | **0** |
| Verified lifecycle events with economics enabled | **0** |
| Verified ticker/class intervals / security IDs | 19 / 10 |
| Review annotations / with `known_on` | 1 / 1 |

The 15 lifecycle records comprise 2 listings, 2 exchange transfers, 3 mergers, 1 split, 3 ticker changes and 4 trading suspensions. The dated review annotation is not an official lifecycle or issuer/share-class certificate. The ticker/class intervals are retrospective mappings; their `verified` status alone does not establish when the evidence was public. [Aggregate machine-readable evidence](../evidence/box-official-evidence-gap-2026-10-16.json) records the pinned database hash and exact counts.

This necessary-gate inventory does **not** prove that every candidate needs a positive event record, that no official publication date exists upstream, or that all candidate identities are wrong. It does show that the current lifecycle table cannot itself certify its verified events as known by each historical decision date. The [120-session reference-support audit](box-candidate-reference-support-2026-10-15.md) likewise found decision-dated CIK/Nasdaq **mirror observations**, not official issuer/class certification. The [PIT database contract](../../docs/PIT_HISTORICAL_DATABASE.md) requires source publication chronology and independent security-class facts; terminal economics remain disabled.

The immutable Train/Validation candidate scans continue independently. To open formal LEAN verification, source-dated official issuer/class and corporate-action evidence must be installed through the existing trust-catalog/master rebuild workflow, then checked against candidate dates and accepted same-source execution prices/actions/factors. This report changes no frozen rule, database, candidate, signal or portfolio result. Since no code changed, the latest full Native-inclusive pytest remains **818 passed, 8 skipped**; it was not repeated for this inventory.

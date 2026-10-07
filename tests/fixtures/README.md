# PIT observation fixtures

`pit-real-observations.csv` is a small factual subset of the first locally built
Security Master (CSV SHA-256
`2aab8aad77fbb61914d74d33bf7f6d41079eb308cada7b803cf20fdb723f28c0`).
It preserves observed symbols, issuer descriptions, exchange and episode bounds
for the dated identity tests. These are historical observations, not official
listing/delisting dates. The primary upstream is
[rreichel3/US-Stock-Symbols](https://github.com/rreichel3/US-Stock-Symbols), pinned
at `157439344501b2020cc2ae37addd6f628fa00699`.

The actual identity/event decisions and raw-document hashes are in
`config/pit_trust_evidence.json`, backed by SEC/issuer/exchange disclosures.
Names select observations; names do not authorize identity merges. Full source
trees, raw documents, normalized master and price databases remain local.

The price importer tests use the real ATVI final OHLCV value from
[post-no-preference/stocks](https://www.dolthub.com/repositories/post-no-preference/stocks)
at `vt6qeesk27k07492k5jc5b7p04mf0s6o`, CC BY-SA 4.0. Their query responses and
adjustment-proof envelopes are explicitly synthetic hostile-input fixtures.
They do not replace the hashed real source responses used for local acceptance.

LEAN examples preserve real rename/split boundaries but include illustrative
sentinel/factor values. They are parser fixtures, never executable certified data.

# PIT to LEAN data design — execution remains blocked

Stock Radar generated evidence is separate from QuantConnect official data.
This document and `radar.pit.lean_plan` describe formats and boundary tests only.
No production map/factor files or terminal settlement models are installed.

## Reviewed native source

Local LEAN source commit: `82810ea63d5542f05dc58f9d1db0557cf174d0ea`.
Primary implementation references:

- [MapFile.cs](https://github.com/QuantConnect/Lean/blob/82810ea63d5542f05dc58f9d1db0557cf174d0ea/Common/Data/Auxiliary/MapFile.cs)
- [CorporateFactorRow.cs](https://github.com/QuantConnect/Lean/blob/82810ea63d5542f05dc58f9d1db0557cf174d0ea/Common/Data/Auxiliary/CorporateFactorRow.cs)
- [DelistingEventProvider.cs](https://github.com/QuantConnect/Lean/blob/82810ea63d5542f05dc58f9d1db0557cf174d0ea/Engine/DataFeeds/Enumerators/DelistingEventProvider.cs)

## Identity and maps

Use stable instrument identity, not one permanent ticker file. Verified FB/META
Class A may share an identity; old Nasdaq BBBY and new NYSE BBBY cannot share it.
CIK identifies an issuer; share class, exchange and dated scopes are required.
Exchange transfer must preserve identity while changing the dated market route.

Map rows are `yyyymmdd,mapped_symbol` (optional exchange/mapping-mode columns
belong to the native row contract). The date is an interval **end**, not the
first effective date of the ticker. `GetMappedSymbol` returns the first row
whose date is at least the search date. `HasData` separately checks the first
and final map dates. The first/final row dates also define `FirstDate` and
`DelistingDate`; observation limits cannot automatically become these dates.

The parser fixture `20220608,fb` followed by `20501231,meta` tests the verified
2022-06-09 ticker transition. Its first row `20210901,fb` marks the research
coverage start; **it does not assert an IPO**, and the 2050 sentinel does not
assert tradability to that date. A future adapter needs explicit source coverage
and actual listing/retirement evidence before producing executable map files.

## Factor rows and price normalization

Corporate factor rows contain `date,price_factor,split_factor,reference_price`.
Native split/dividend application places a factor change on the previous
trading day, using exchange hours. For NVDA's trading split on 2024-06-10, that
boundary is 2024-06-07. The test `20240607,1,0.1,1208.88` demonstrates parsing;
the `1` price factor is illustrative and does not certify dividend history.

Store raw bars and complete dated corporate actions, then validate raw,
split-adjusted and dividend-adjusted series independently. Do not feed already
split-adjusted Stock Radar research bars through another split adjustment.
Do not derive general factors from one split probe. Current public-source
acceptance supports only reviewed no-split lifetimes; general normalization
remains blocked.

## Delisting events and economics

The reviewed native provider emits Warning at/after the map delisting date and
Delisted after it, carrying the last observed price or zero if no prior data.
That provider field is **not evidence of economic payout**. Native event timing
must be reconciled with an independently verified last tradable session,
suspension, legal removal, merger completion and settlement date.

ATVI/TWTR/SPLK disclosures document cash consideration, but entitlement,
settlement timing, fees, cancellation/conversion and portfolio accounting are
not implemented or verified. Last closes 94.42/53.70/156.90 are market prices,
not 95/54.20/157 settlement models. Bankruptcy does not imply an automatic zero;
exchange suspension may continue OTC; ticker/brand reuse is a different security.

## Gates before an executable adapter

All ten portfolio gates in the PIT readiness scorecard must be established for
the requested universe and holding lifetimes: unambiguous signal identity,
identity-bound execution bars, reliable symbol maps, validated split factors,
complete position prices, explicit delisting events, supported terminal
economics, complete provenance, real golden cases, and native result parity.
The nine current real cases validate membership/research boundaries; they do
not certify all ten gates. Existing LEAN PIT rejection stays active. Current
Snapshot native golden/parity/cancellation regressions remain parallel.

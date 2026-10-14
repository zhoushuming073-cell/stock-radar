# Box Stage D candidate execution-metadata follow-up

The existing 43-task horizon audit established a raw execution-price gap on
a small nonrepresentative labeling pool. Extend that **metadata-only** audit
to every near-lower candidate on two already verified, complete Train and
Validation days. This measures a different population without turning a
detector context into a trade signal.

1. Bind each input day to the private immutable candidate file-set hash and
   recomputed RI/config/code selection. Preserve each candidate's exact
   source, basis, decision date and frozen split boundary.
2. Reuse the existing `horizon_metadata` and `summarize` functions; read only
   subsequent session availability, source/basis, readiness, identity and
   corporate-action flags. The ten-session length is a coverage diagnostic,
   not a selected holding period. Do not read future OHLCV values or outcomes.
3. Save private row-level receipts only beneath ignored local `data` and
   publish aggregate counts. Test duplicate/missing candidate mapping and
   run full project regression with Native LEAN opt-in.
4. Report the distinction between same-source raw coverage and alternative-
   source raw rows. Do not treat split-adjusted research rows or an alternative
   source as a formal executable price. No LEAN/QC backtest is authorized by
   this check.

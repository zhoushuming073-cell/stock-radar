# Box free-source candidate evidence pilot — 2026-10-21

**Authorization:** owner chose the free-data route and on 2026-10-21 explicitly directed Codex to verify existing candidates against dated public identity/event evidence and same-source prices, isolating unresolved cases.

## Scope

- Keep Research Infrastructure v1, sealed Train/Validation candidates, and accepted-price stores read-only.
- Check three spaced Validation sessions in the public NYSE CTA symbol-file window: 2025-05-05, 2025-07-01, 2025-09-08.
- Extend symbol-snapshot coverage to every frozen Validation session in that public CTA window, with complete file-set rehashing. Keep the three-day deeper issuer/price/SEC pilot distinct from the full-window symbol audit.
- Bind each aggregate to the sealed candidate-day hash; compare exact-case historical symbols only.
- For raw-source candidates, intersect existing as-of-T issuer observations, accepted T-day OHLCV, and ten-session same-source raw availability metadata.
- Review pre-T SEC cover-page class/symbol/exchange evidence for a bounded private follow-up subset.
- Keep symbols, CIKs, security IDs, raw files and candidate-to-filing mappings in ignored local data. Commit only code, tests and aggregate evidence.

## Gate

CTA symbol presence and SEC cover-page evidence are scoped observations. They do not by themselves establish complete issuer lifecycle, every corporate action, accepted raw execution prices through a holding period, or LEAN readiness. No outcomes, Test/Fresh, signals, portfolio trades or returns may be used in this pilot.

**Outcome:** [acceptance](../../reports/acceptance/box-free-cta-sec-pilot-2026-10-21.md). Formal box LEAN remains deferred.

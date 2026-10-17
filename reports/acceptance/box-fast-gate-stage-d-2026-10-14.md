# Box Stage D necessary-gate audit — 2026-10-14

**Result: the T-only gate rejected 2,723/3,944 eligible rows on one complete
Train day without excluding any of the 96 actual near-lower rows.** This is a
candidate retrieval precondition, not a full detector-state replacement,
structure-accuracy estimate, trade signal or return result.

`assess_lower_band` can return `NEAR_LOWER_STABILIZING` only when the final
session gain, three-session gain, final-session decline, recent-low change,
volume baseline and recent volume ratio pass its versioned bounds. The new
`necessary_near_lower` evaluates precisely these **necessary** T-known
conditions on a homogeneous 20-session prefix. A small tolerance makes
exclusion conservative at numeric boundaries. Any missing, nonfinite,
noncontiguous or source/basis-untrusted prefix is retained for the full
provider rather than silently excluded.

The audit bulk-read only sessions at or before T from frozen Research
Infrastructure v1. It joined all supported/ready 126-session rows on
2024-07-01 to their last 20 bars, then verified the existing 16-chunk full
detector receipt and compared private identities in memory. No post-T price,
outcome, human label, Test or Fresh observation was read.

| Real Train date 2024-07-01 | Result |
| --- | ---: |
| Full eligible denominator | 3,944 |
| Trusted 20-session prefixes / unknown retained | 3,944 / 0 |
| Certainly cannot enter near-lower state | 2,723 (69.0%) |
| Still requires both full detectors | 1,221 (31.0%) |
| Full-day detector near-lower union | 96 |
| Known near-lower rows wrongly excluded | **0** |

The reason counts overlap; they are not separate excluded populations. The
largest count is final-session decline (2,274), followed by recent-low
decline (654), volume spike (450), three-session extension (163), one-session
extension (115) and unavailable volume baseline (9). The exact aggregate,
code/config/RI hashes, runtime versions and sealed full-scan file-set hash are
in [public evidence](../evidence/box-fast-gate-stage-d-2026-10-14.json).
No security/date mapping or OHLCV value was committed.

This gate preserves the target state by construction under the current Stage C
rules and retained-unknown policy. The one-day comparison catches a concrete
implementation mismatch but is not a multi-year prevalence or performance
estimate. The full-state scanner remains the reference. A separate candidate-
only resumable path must be implemented and benchmarked before extrapolating
the observed 69.0% rejection to all Train/Validation sessions. Issuer identity,
raw execution prices and formal LEAN rules remain open.

Focused necessary-gate tests: **3 passed**. Full project pytest with
`STOCK_RADAR_TEST_LEAN=1`: **784 passed, 8 skipped, 1 existing
`websockets.legacy` warning** in 105.62 seconds. Native LEAN regression was
enabled; no box portfolio backtest was run.

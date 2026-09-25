# Strategy 2 portfolio development review — before final Test

The simulator starts each segment with $1,000,000, uses next-session Open
entry, Open/Close exits (+5%, -10%, 10 sessions), whole shares, no leverage,
up to three new candidates per day, no pyramiding, the configured gap gate,
and separate buy/sell fees plus 10 bps slippage on each side. Signals use the
2,000-symbol current-snapshot research cohort; explicit ETF/ETN names are
excluded by a limited name rule. All results here are **Train and Validation
only**. The final Test has not been loaded.

| Rule / allocation | Train net return | Train max DD | Validation net return | Validation max DD |
|---|---:|---:|---:|---:|
| Combined Elasticity and pullback rank / equal cash | -81.14% | -83.51% | +4.49% | -65.24% |
| Deepest pullback rank / equal cash | -61.59% | -77.96% | +37.10% | -44.37% |
| Elasticity rank / equal cash | -93.29% | -93.54% | -13.83% | -76.08% |
| Combined rank with reversal confirmation / equal cash | -84.63% | -85.74% | -26.01% | -62.86% |
| Deepest pullback rank, SPY ≥ MA200, 33.3% cap | -48.61% | -67.99% | +6.26% | -42.47% |
| Trend/pullback/reversal rule / equal cash | -72.36% | -78.03% | -36.15% | -65.73% |

The alternative score-weighted allocators changed outcomes little. A 25%
single-position cap and a causal SPY 200-session moving-average gate reduced
some losses but did not produce stable positive Train/Validation returns.

For the predefined combined/equal baseline, 2022 trades lost about $723,176
net. Stop exits and gap-through-stop losses outweighed many take-profit trades.
Its trade-level and portfolio accounting reconcile to below $0.000001; cash
stayed nonnegative. The large drawdowns are a strategy risk in this data, not
an accounting discrepancy found by the reconciliation checks.

**Decision before Test:** No researched candidate passes a conservative
stability standard. The original combined/equal baseline is frozen only as a
one-time diagnostic to satisfy the requested complete backtest. It was
declared before Validation results and will not be retuned after Test. The
current trading recommendation is **CASH / do not deploy** unless future
research yields a new candidate and a fresh untouched test period.

The uSMART fee profile in this run is illustrative and unconfirmed. Historical
survivorship, incomplete security classification, split-adjustment anomalies,
fixed-bps slippage and lack of intraday sequence data remain material limits.

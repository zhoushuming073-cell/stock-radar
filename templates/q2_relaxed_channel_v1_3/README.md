# Q2 Relaxed Channel v1.3.0

Exploratory candidate selector `q2_relaxed_channel_v1_3` / `high-beta-liquid-channel-v1.3`.
It requires the Stock Radar Research Infrastructure v1 history backend and a
dated historical security ID. Every decision uses data available by signal day
**T close**. This is not a profitability claim.

Market gate: SPY beta over 126 paired sessions >=2.0 and 20-session average
`close * SIP volume` >=USD 50m. Preferred tier: beta >=2.5 and ADV >=USD 100m.
Valid channels may be any single weekly 12/16/20/26 or monthly 9/12/15/18
window, with >=1 complete swing, clarity >=55, normalized 126-session drift
-15% to +25%, and log channel position <=55%. 0-35% is preferred. At least
one of four causal readiness confirmations is required. A rise >8% in one day
or >15% in five days waits; severe downside acceleration and a structural
breakdown are rejected. Ranking uses 50% structure, 25% readiness, 15% lower
position, 10% preferred market tier; maximum 10 candidates per signal day.

The host owns cash, position limits, sizing, fees, slippage and orders. Earliest
entry is the next session open; maximum holding period is 10 sessions. No
optimized take-profit or stop-loss is set. Check the Run's actual host
execution settings before starting. Prices are split-adjusted daily bars and
LEAN uses open/close proxies, with no intraday path. The frozen historical
membership reduces survivor bias but does not remove unknown identities or
all historical coverage limits. SPY comes from the separate SIP benchmark
store; its absence explicitly excludes a beta observation.

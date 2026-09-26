# Full Strategy 2 v1

Official migration of the Phase 2 seven-stage candidate strategy. It reuses
`radar.strategy.full_strategy2.score_full_strategy2` to preserve signal logic.
Only the signal thresholds in `strategy.yaml` are editable. Position sizing,
entry/exit timing, take profit, stop loss, holding period, cash and costs remain
controlled by the Stock Radar backtest engine.

The seven groups are prior strength, pullback quality, downside exhaustion,
support/absorption, stopped new lows, early reversal, and not extended.
Historical Test was previously viewed and remains exploratory.

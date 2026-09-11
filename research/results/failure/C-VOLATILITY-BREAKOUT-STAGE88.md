# C Stage88 volatility-compression breakout — failed

- Research only; no A/B/live changes.
- Method: identify completed-hour volatility in the lowest prior-720-hour percentile, require a 24/72-hour range breakout and 1.0/1.5x volume, enter next hourly open, hold 3/6/12/24 hours.
- Universe: ADA, ATOM, FIL, XLM, AAVE, ETC.
- Grid: 288 rules per symbol; rules nominated independently by each chronological third and replayed unchanged on all thirds.
- Passing rules: 0.
- Numerically best full-period rule: XLM, 72h volatility, bottom 10% compression, 72h breakout, 1.5x volume, 3h hold, 3x leverage.
- Best full result: 178 trades, 47.75% win rate, $100 -> $273.02, +173.02%, MDD -34.47%.
- Three thirds: -26.04%, +138.28%, +54.93%. It fails transferability because the first third loses.
- Double-cost result: +55.96%, MDD -40.93%.
- Decision: reject as A/B addition and as a C plan. Do not deploy.

Evidence: `research/results/volatility_breakout_stage88/results.json`

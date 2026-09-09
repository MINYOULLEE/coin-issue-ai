# B ALGO + ADA Stage92 execution verification

## Verdict

Historical execution-proxy validation passed for the live entry TTL, but this remains research-only and is not deployed. It is not an untouched forward test or an actual BingX fill test.

## Candidate

- Current B Stage66 plus ALGO 3h 8% capitulation/50% wick with volume threshold 1.0x instead of 1.5x.
- ADA UTC 06/07/08 completed-hour 3% shock reversal, next-open entry, 7h hold, isolated 3x, 25% target margin.
- Stage91 hourly result: 995 trades, 55.68% win rate, $100 -> $6,858,952.97, +6,858,852.97%, hourly mark MDD -54.65%, adverse bound -62.05%.

## Binance USD-M perpetual minute replay

All 54 candidate windows (ALGO 25 + ADA 29) were downloaded without gaps. No orders or credentials were used.

| Entry delay | 5y compound return | Trades | Hourly mark MDD | Adverse bound | Liquidation proxy |
|---:|---:|---:|---:|---:|---:|
| 0m | +6,666,302.64% | 995 | -54.65% | -62.63% | 0 |
| 1m | +7,231,874.38% | 995 | -54.65% | -61.31% | 0 |
| 3m | +5,938,518.38% | 995 | -54.65% | -63.61% | 0 |
| 5m stress | +5,795,664.86% | 995 | -56.08% | -66.77% | 0 |
| 10m stress | +4,685,624.07% | 995 | -59.76% | -69.56% | 0 |

Only delays strictly below 5 minutes qualify under the existing B TTL. All qualifying delays remain above the current Stage66 +4,556,211.86% reference and within the -70% research bound.

## Collision and margin

- Candidate opportunities: 54.
- Same entry boundary with existing B: 7.
- Holding-overlap pairs with existing B: 29.
- Candidate-to-candidate overlap pairs: 2.
- The frozen reserved-margin replay proportionally clipped simultaneous demand; it did not use leverage fallback. Result: margin-clipped 884, rejected 21, liquidation proxy 0.
- A is a separate account, so A/B symbol-time overlap does not share credentials, positions, collateral, or orders.

## Test status

- Reserved-margin unit tests: 2/2 pass.
- B sizing tests: 5/5 pass.
- Full frozen-file audit: blocked by a pre-existing `docs/index.html` hash mismatch caused by the added `exchange-guide.html` UI link. No strategy standard was changed by this research, and the UI change was not reverted.

## Remaining truth boundary

- No untouched forward holdout.
- Binance futures public minute bars are not BingX fills or order-book depth.
- No actual orders, deployment, standard update, or live switch change.

Evidence: `research/results/b_algo_ada_futures_stage92/results.json`

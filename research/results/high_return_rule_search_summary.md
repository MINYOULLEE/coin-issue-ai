# High-return rule and portfolio search

Gate fixed before evaluation:

- five-year compound return at least +10,000%
- five-year MDD no worse than -50%
- independent final 30% profitable
- independent final 30% MDD no worse than -50%

The search covered 17 coins and trend, EMA, channel breakout, RSI trend,
RSI mean-reversion, long-only, short-only, both sides, volatility targeting,
drawdown deleveraging, and 1x-4x exposure. No individual strategy passed.

Best train-selected examples:

| Symbol | Five-year | MDD | Independent 30% | Result |
|---|---:|---:|---:|---|
| DOGE | +1,625.78% | -63.73% | +42.11% | fails return and MDD |
| ICP | +1,076.15% | -78.26% | -52.50% | fails |
| FIL | +691.78% | -72.25% | -65.98% | fails |
| ETC | +461.55% | -65.24% | -56.93% | fails |
| ADA | +366.26% | -34.38% | +65.47% | stable but return too low |
| AVAX | +349.65% | -85.76% | -75.56% | fails |
| XLM | +303.27% | -37.16% | +20.51% | stable but return too low |
| ATOM | +309.60% | -41.56% | +32.53% | stable but return too low |

Portfolio search combined 2-5 strategies and 0.5x-3x portfolio scaling. The
highest-return train-selected portfolio produced +193,543.50% over the full
period, but MDD was -91.73% and the independent period lost -83.43%. After
hard-filtering training MDD above -50%, no evaluated portfolio satisfied the
full-period and independent-period gates.

Conclusion: this family of simple rule strategies does not meet the user's
high-return requirement. It must not be deployed. The next research family
needs state-dependent multi-strategy switching or different intraday execution,
not more leverage on these rules.

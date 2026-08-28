# Repair study: XLM, BCH, DOGE, ATOM

The repair search varied forecast horizon (6/12/24/48/72 hours), long/short/both
directions, confidence thresholds, exposure, tree depth, and leaf size. Model
selection used three expanding validation folds; the final 15% was untouched.

| Symbol | Corrected rule | Five-year in-sample | Five-year MDD | Worst validation | Untouched holdout | Holdout MDD | Gate |
|---|---|---:|---:|---:|---:|---:|---:|
| XLM | 24h, long-only, 0/0.25/0.5x | +51.53% | -7.45% | +0.29% | +2.96% | -5.63% | FAIL |
| BCH | 24h, long-only, 0/0.5/1x | +68.56% | -3.57% | +11.92% | +2.65% | -12.16% | FAIL |
| DOGE | 12h, long-only, 0/0.25/0.5x | +12.20% | -12.68% | +6.75% | -4.94% | -4.94% | FAIL |
| ATOM | 6h, long-only, 0/0.25/0.5x | +43.40% | -6.77% | +0.40% | -0.72% | -8.09% | FAIL |

XLM and BCH were partially repaired: removing shorts and reducing exposure cut
drawdown materially. Their untouched returns, however, remained below the 5%
promotion threshold. DOGE and ATOM failed the untouched period. No candidate is
approved for portfolio combination or live deployment.

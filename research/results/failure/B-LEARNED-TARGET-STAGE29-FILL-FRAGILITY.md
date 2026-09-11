# B q80 target — strong execution-robustness claim not supported

2026-09-01. [Full report](../learned_targets_stage29/REPORT.md).

The hypothesis that the full 43.8% ending-equity improvement is robust to target fill assumptions is not supported. At 5bp (0.05%) overshoot required before crediting a fill at target, ending equity drops to $1,730,595.74, +1,730,495.74%, 738 trades, 57.32% wins, hourly mark MDD -57.48%. Baseline ends at $1,717,526.82 and -55.36% hourly mark MDD: only about 0.76% more ending capital, worse drawdown.

This is NOT a claim of negative absolute return, nor that all variants failed. Delayed market-exit proxy scenarios still exceed baseline. It is a reason to keep adoption on hold pending realistic trigger-market/limit-fill, spread, depth and futures basis checks. Overshoot is a sensitivity assumption, not a calibrated queue-fill model.

Of 55 original target-hit opportunities, 3 never overshoot enough within the original holding horizon and 13 meet that stricter condition later. No parameter was changed in the live A/B plans.

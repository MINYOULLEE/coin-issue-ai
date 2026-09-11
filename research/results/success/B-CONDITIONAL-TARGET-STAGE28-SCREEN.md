# B Stage28 — provisional research screen, NOT deployment approval

2026-09-01. Current B Stage26 entry signals, opportunity cooldowns and reservation model preserved. A excluded pending replay reconciliation. No production changes.

Source: [full report](../conditional_exits_stage28/REPORT.md), [results](../conditional_exits_stage28/RESULTS.json), and per-rule files with ledgers and decision-time training provenance.

Only profit targets learned from prior completed same-symbol/same-direction baseline net-winning opportunities pass the first screen. Last 120 completed opportunities, minimum 20 winners; target = quantile of prior maximum favorable excursion / prior ATR, multiplied by current ATR. No added stop. Prior planned exit remains the deadline. Opportunities without enough history keep baseline exits.

- q50: +2,099,428.09%; $100 -> $2,099,528.09; 739 trades; 58.05% wins; hourly mark MDD -59.46%.
- q80: +2,470,260.80%; $100 -> $2,470,360.80; 739 trades; 57.37% wins; hourly mark MDD -57.48%; closed balance MDD -46.72%.
- q95: +2,087,570.28%; $100 -> $2,087,670.28; 736 trades; 56.93% wins; hourly mark MDD -55.75%.
- Baseline: +1,717,426.82%; $1,717,526.82; 736 trades; 56.93% wins; hourly mark MDD -55.36%.

q80 double-cost return +83,955.68%, baseline +58,361.78%. q80 improves two of three chronological thirds, NOT the first. 353/756 complete opportunities have enough learning history; q80 target touched on 55 candidate opportunities, not necessarily 55 filled trades. One incomplete-candle opportunity excluded from training only.

All 13 tested variants and all thresholds were considered on previously explored data. Passing is not independent validation or live suitability. Costs are static assumptions on Binance spot OHLC, not actual BingX historical futures execution. Intrahour target fills, actual funding, mark-price liquidation and live parity remain unverified. Do not deploy from this file or replace frozen standards.

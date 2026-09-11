# A/B adaptive exits Stage27 — rejected screen

2026-09-01. Research only; no live settings or production code changed.

See [full report](../adaptive_exits_stage27/REPORT.md) and [machine-readable results](../adaptive_exits_stage27/RESULTS.json).

Tested 11 adaptive exit rules plus baseline for each plan, each with full-period, double-cost and three chronological segment replays (120 runs). Prices derive from completed-bar ATR, recent structure, mean reversion targets, trailing exits, holding-horizon-adjusted distances and conditional signal-type selection. All new variants underperformed their same-model baseline; all three discovery segments selected baseline for both plans. No successful candidate.

B Stage26 original reference reproduced exactly. Best new B full-period variant was horizon_trail: +88,920.44%, $100 to $89,020.44, 742 trades, 56.60% wins, hourly mark MDD -69.93%. Original baseline: +1,717,426.82%, $1,717,526.82, 736 trades, 56.93% wins, hourly mark MDD -55.36%.

A comparison requires special caution: its historical constant-weight headline is not the fixed-entry-quantity comparator. The latter additionally applies explicit costs and an approximate isolated-margin liquidation rule. Baseline proxy events: 315. These are modeled events, NOT verified actual BingX liquidations or proof of a live bug. A new variants do not improve this comparator and are not deployable findings.

Do not repeat this exact grid as a new discovery. Possible different follow-up: signal-specific adverse/favorable excursion distributions with causally calibrated conditional quantiles, followed by lower-timeframe execution checks; first reconcile A replay with the actual executor. None of that follow-up is claimed completed here.

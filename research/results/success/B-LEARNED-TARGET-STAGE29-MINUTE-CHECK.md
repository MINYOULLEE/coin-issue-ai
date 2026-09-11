# B learned q80 target — minute-touch reproduction only

2026-09-01. [Full report](../learned_targets_stage29/REPORT.md), [results](../learned_targets_stage29/RESULTS.json).

All 55 target-touch opportunity windows downloaded as public Binance spot 1m candles: 220 full hours, 13,200 minutes, zero original-hour OHLC mismatches. Frozen Stage28 decisions exactly reproduced before the minute check. Target-touch at the same raw target reproduces +2,470,260.80%, $100 -> $2,470,360.80, 739 trades, 57.37% wins, hourly mark MDD -57.48%.

Minute-touch timing only validated, not exchange execution. The entire account remains hourly for reservations, funding and equity evaluation. No live changes and no A rerun.

Status: PARTIAL RESEARCH PASS, NOT LIVE ADOPTION. See the paired failure/fragility note: requiring 5bp overshoot removes nearly all baseline advantage. Do not claim all execution tests established robustness.

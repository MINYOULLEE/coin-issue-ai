# 2026-08-28 initial research findings

## Data

- Binance official hourly candles: 2021-08-28 through 2026-08-28
- 43,824 candles each: BTC, ETH, XRP, TRX, SOL, BNB
- Deployed 35-feature formulas and the five serialized trees were read directly
  from the live source files.

## Existing MDD30 replay audit

The prior claimed live-input result (`+799,385.16%`, MDD `-29.22%`) is not yet
reproducible from the source artifacts currently in Git.

Using the deployed rolling-1,000-hour feature implementation, completed 00:00
UTC candle, next-hour execution, and no fees produced:

- hourly mark-to-market: `+418,296.41%`, MDD `-35.14%`
- daily fixed-notional accounting: `+382,721.74%`, MDD `-32.66%`

This is not evidence that either number is the correct historical result. It is
evidence that an uncommitted part of the original research ledger (accounting,
warm-up, sampling, or execution convention) is still missing. New assets must
not be compared against the old headline number until that convention is
recovered or deliberately replaced by the audited replay convention.

## BNB first pass

The answer-sheet fit generated huge in-sample results, but failed out of sample.
The first 55/15/30 split selected a model that returned `+276.75%` in validation
and then lost `-87.46%` in the independent final 30% (MDD `-87.92%`).

A stricter three-fold expanding walk-forward selected a conservative model:

- neutral band: 1.0%
- tree depth: 3
- minimum leaf samples: 20
- confidence thresholds: 60% / 75%
- exposure: 0 / 0.25 / 0.5
- worst validation fold: `-1.22%`, MDD `-4.26%`
- untouched final 15%: `-4.12%`, MDD `-4.12%`

Promotion gate: **failed**. BNB should not be added to live MDD30 in this form.

## Next research action

Build the same walk-forward batch report for the remaining liquid coins, keep
only assets that pass the untouched holdout gate, then run portfolio-level
correlation and MDD optimization. Overseas futures remain a separate dataset and
execution-cost model and must not share crypto assumptions.

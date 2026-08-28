# MDD30 research workspace

This directory contains reproducible, offline-first research code for the
deployed `answer_mdd30` strategy. It does not modify or deploy the live trading
functions.

## Baseline replay

```powershell
python research/scripts/replay_mdd30.py --symbols BTC ETH XRP TRX SOL BNB
```

The script downloads completed Binance hourly candles into `research/data/`,
reads the five deployed decision trees directly from
`supabase/functions/coin-collector/answer_trees.ts`, and writes results under
`research/results/`.

BNB has no deployed tree yet. Its candles are downloaded for the next training
step, but it is excluded from baseline replay until a model is trained.


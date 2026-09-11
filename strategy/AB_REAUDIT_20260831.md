# A/B re-audit — 2026-08-31

Scope: user requested research replay and missing-path audit. No production code, scheduler, trading switches, credentials, or exchange orders changed. Local diagnostic only; no deployment/commit/push performed for this audit.

## Verification performed

- Existing 37 Node tests passed; two Python reserved-margin tests, 24-file baseline audit and UI control tests passed.
- Replayed stored A five-asset data in memory using current `replay_mdd30.targets/replay/replay_daily`; did not overwrite adopted results.
- Replayed B using `replay_reserved_margin_stage16.prepare/replay` at weight 1.15; did not overwrite adopted results.
- Read actual deployed `bingx-order-submit`, `coin-collector`, and `telegram-trade-notify`; inspected production cron/state and A decision audit read-only.
- Ran `research/scripts/diagnose_a_submit_20260831.cjs`: real A submit source evaluated with fully mocked HTTP and environment. No network allowed by the fixture.

## Findings (not corrected in this inspection)

### P1 — A ambiguous order acceptance releases its reservation

`supabase/functions/bingx-order-submit/index.ts`: `orderAccepted` is set only after the POST returns. Simulating an exchange-accepted POST whose response times out produces HTTP 502, zero order lookups, reservation DELETE and no durable trade record. A real order could remain untracked while its signal is invalidated. Needs durable intent + lookup/reconciliation before reservation release, not blind resubmission.

### P1 — A zero execution can be recorded as a filled position

Same function: after lookup reports `status=NEW, executedQty=0, avgPrice=0`, fallback replaces the price/quantity with the requested values. Diagnostic reproduces HTTP 200 and an `open` trade for requested quantity 0.01, despite no confirmed fill. Must distinguish pending, partial and completed fills.

### P1 — A daily completion still trusts asynchronous queue acceptance

`bingx-order-execute` returns `{ok:true,queued:true}` after `EdgeRuntime.waitUntil` dispatch. Collector's `enter` accepts this as entered and can commit `last_mdd30_decision_closed_at`. A later submit-worker failure is not carried into that daily completion decision, so the earlier retry fix does not cover the actual asynchronous worker failure. Needs per-symbol durable completion status, not queue acceptance as execution success.

### P1 — B Telegram close notification is incompatible with deferred settlement

Actual deployed notifier queries all `status=closed` B trades without requiring final `net_pnl_usd`/`close_price`. It converts `Number(null)` to zero and advances `last_pb_closed_at` immediately. New executor intentionally writes closed/net=null before fetching exchange settlement. The notifier can therefore report zero PnL prematurely and skip a later correction using the close-time cursor. Need settled-only notification and per-trade delivery tracking. Existing notifier source in the local checkout also differs from deployed B-aware notifier; local-only audit does not cover it.

### P2 — A displayed decision time differs from observed execution

`PLANS.md` and UI say UTC 00:00 / Thailand 07:00. Collector tests the hour of Binance candle close timestamp (00:59:59.999), then acts after it closes. Production audit: `closed_at=2026-08-30T00:59:59.999Z`, `checked_at=2026-08-30T01:00:11.757Z` (Thailand 08:00:11). Research `targets(...,0)` likewise uses the candle opening at UTC00 and enters at UTC01. Therefore this is not evidence of random one-hour latency; the written/displayed convention conflicts with code/replay. Correct wording or explicitly authorize a strategy-time change; do not silently shift the strategy.

### P2 — A reported replay is not fixed-quantity live execution

A `hourly_mark` compounds hourly target-weight returns, while live code keeps quantities when direction/exposure settings do not change. The existing `daily_fixed_notional` replay also resets daily weights and records only decision-boundary drawdown. Neither establishes exact live-path parity. Treat reproduced numbers as those simulations, not an end-to-end live certification. B replay still omits actual historical contract minimums, maintenance tiers, exchange mark prices and signal scheduling/order-race parity.

## Recomputed research numbers (initial $100)

| Model | Final USD | Cumulative return | Maximum drawdown | Count |
|---|---:|---:|---:|---:|
| A existing hourly target-weight simulation | 257,697.52 | +257,597.52% | -35.53% hourly equity | 2,631 target changes, NOT verified completed trades |
| A existing daily fixed-notional simulation | 233,652.24 | +233,552.24% | -33.08% decision-boundary equity only | 2,630 target changes |
| B adopted Stage16 reserved-margin simulation | 516,614.04 | +516,514.04% | -49.00% after closed trades; -54.64% hourly equity | 656 closed trades; 56.71% wins |

B conservative sum of hourly adverse extremes: -61.30% (not simultaneous tick drawdown). Liquidation proxy count 0; this does not prove actual-exchange liquidation safety. B clipped 656 entries and rejected 21 opportunities. B live performance baseline remains $150; research remains $100.

## Current operational state observed

At database UTC 2026-08-30 21:04, B `enabled=false`, `test_mode=false`, entry cron inactive; signal and close cron active. This audit did not change them. No B signals/trades stored. A audit lists all five current positions held. Snapshot heartbeat continued to update.

Conclusion: stored research results reproduce and existing tests pass, but additional execution/notification defects are confirmed. Do not label the whole system error-free or fully live-validated.

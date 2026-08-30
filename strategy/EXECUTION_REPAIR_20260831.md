# A/B execution safety repair — 2026-08-31

User authorized correction of all findings from the deployed-source audit.
No strategy thresholds, research returns, A trees, A 10x/1.6 exposure, or B Stage16 sizing constants changed.

## Follow-up: account configuration correction (2026-08-31)

The user asked to make the remaining configuration normal. Executor v10 adds scheduler-authenticated, configuration-only leverage alignment while the entry gate is locked. It refuses unknown/A symbols, pending B intents, tracked open trades, exchange positions or open orders; it cannot change margin/position mode or place orders through this action.

- Actual exchange LONG/SHORT leverage changed from 20/20 to AVAX 3/3, ICP 5/5, BCH 3/3, DOGE 5/5, UNI 2/2; each write was followed by a successful exchange readback. Request IDs: 18164, 18169, 18170, 18175, 18176.
- Exchange `openOrders` returned `{orders:[]}`, not the bare array described by the reference; both explicit shapes are supported and unknown shapes still block writes.
- GET rate-limit responses (100410) retry at most twice with backoff; writes never blindly retry. Per-endpoint read pacing reduces bursts but is not a distributed account-wide limiter.
- Preflight now reports `ok=false` if any configuration check fails, rather than falsely returning top-level success.
- Final read-only preflight request 18177: HTTP 200, ok=true, all five configuration checks passed, orders_submitted=0. Previously observed leverage mismatches and rate-limit responses were absent in this check.
- 37 Node regression tests, two Python reserved-margin tests, separation audit and UI controls tests passed. Deployed v10 source/dependencies were read back and matched the local bundle.
- No entry or exit orders were submitted during this repair. B entry runtime gate remains false and entry cron remains paused; configuration correction is not a claim of completed live fills or an automatic trading restart.
- API reference: https://github.com/BingX-API/api-ai-skills/blob/main/skills/swap-trade/api-reference.md
- Rate-limit reference: https://github.com/BingX-API/api-ai-skills/blob/main/skills/references/rate-limits.md

## Initial deployment (historical; follow-up above supersedes B executor/configuration status)

- A collector v74: daily decision commits only after all assets succeed/hold/cash; failed assets can retry within the decision window.
- A executor v62: close uses actual remaining quantity and verifies zero remainder; no symbol-wide income sum assigned to a single trade. Existing position-history synchronization supplies final settlement.
- B strategy v5: operational run/preview uses the checked-in, tested shared signal implementation; deployment bundle contains only required dependencies.
- B executor v7: common batch sizing plus existing atomic reservation/claim RPCs, checked leverage, no simulated live ledger rows, unknown-order reservations retained, exit management independent from entry switch, persistent close attempts and residual quantity confirmation, exchange-net settlement only.
- B account API v9: shared runtime entry gate exposed to dashboard status; finalized, verified records only in performance statistics.
- Database repair: `supabase/repairs/plan_b_safety_20260831.sql` (close-attempt columns and settled-only history statistics).

## Initial operational limitations (historical; configuration issues resolved above)

- B entry scheduler job 5 (`plan-b-executor-execute`) paused for maintenance. B close scheduler and A operation remain enabled.
- B database enabled=true/test_mode=false was not treated as proof of readiness.
- Shared `supabase/functions/_shared/plan_b_runtime.json` has live_ready=false. This is the runtime gate; strategy JSON retains the historical research baseline.
- Automatic approval review rejected the deployment that would permit re-enabling B through the control API. Explicit user approval is needed to unlock/restart B entries. Do not work around this via another API or database path.
- Read-only preflight: AVAX and ICP leverage mismatched; BCH/DOGE/UNI reads returned BingX code 100410. These are blockers, not a successful live certification.
- Unknown submissions retain reservation and require exchange reconciliation; not-found alone does not justify a blind retry. A stopped process before a confirmed close submission may therefore require review.
- B settlement remains pending (null, not zero) when exchange netProfit/history matching is unavailable or ambiguous. No gross PnL is labeled net.
- Local fault-injection/regression suite: 31 tests passed. No real entry/exit was placed for testing.
- Final checks: frozen-file separation audit, two reserved-margin Python tests and dashboard control tests passed. All five repaired deployed functions and their bundled dependencies were read back and matched local source fingerprints after normalizing line endings and trailing file whitespace.

## Persistent source reconciliation

The prior local-only freeze audit passed while remote B code differed. Repaired execution modules, runtime gate, SQL repair and fault-injection tests are now part of the freeze manifest. Hash changes are authorized execution corrections, not adoption of a new trading strategy. Research artifacts not involved in this repair are preserved.

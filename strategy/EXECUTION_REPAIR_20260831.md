# A/B execution safety repair — 2026-08-31

User authorized correction of all findings from the deployed-source audit.
No strategy thresholds, research returns, A trees, A 10x/1.6 exposure, or B Stage16 sizing constants changed.

## Deployed

- A collector v74: daily decision commits only after all assets succeed/hold/cash; failed assets can retry within the decision window.
- A executor v62: close uses actual remaining quantity and verifies zero remainder; no symbol-wide income sum assigned to a single trade. Existing position-history synchronization supplies final settlement.
- B strategy v5: operational run/preview uses the checked-in, tested shared signal implementation; deployment bundle contains only required dependencies.
- B executor v7: common batch sizing plus existing atomic reservation/claim RPCs, checked leverage, no simulated live ledger rows, unknown-order reservations retained, exit management independent from entry switch, persistent close attempts and residual quantity confirmation, exchange-net settlement only.
- B account API v9: shared runtime entry gate exposed to dashboard status; finalized, verified records only in performance statistics.
- Database repair: `supabase/repairs/plan_b_safety_20260831.sql` (close-attempt columns and settled-only history statistics).

## Current operational limitations — do not describe as fully live-verified

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

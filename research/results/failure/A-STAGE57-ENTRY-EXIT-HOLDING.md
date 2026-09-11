# A Stage57 — screened out under the common research engine

Tested eight individual non-sizing changes against unchanged A signal weights:
prior 1h/6h directional confirmation, opposing 6h movement exit, 24-bar mean exit,
and 6/12/24/48-hour maximum holding. All eight have lower full-period returns
than the common baseline. Do not combine or adopt these exact rules as improvements.

Evidence: `../a_stage57/results.json` and per-policy ledgers.
Baseline +23,901.26%; best alternative (6h confirmation) +12,635.35%.
This baseline includes research 1.4 admission limits and is NOT unchanged live A.
Current contract rules, spot OHLC, assumed funding and liquidation proxies apply.
Gaps are listed in results; absent preceding-hour indicators are not fabricated.
All thirds used for discovery, not independent validation. No live changes.

Tests: baseline reproduces Stage53; cash/ledger reconciliation in every replay;
policy timing/blocked same-boundary re-entry tests pass. These are software tests,
not proof of profitable or safe exchange execution.

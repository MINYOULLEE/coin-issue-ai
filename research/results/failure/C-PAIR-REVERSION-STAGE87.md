# C pair-reversion Stage87 — rejected

- Research only; no deployment or live-state change.
- Method: equal-notional market-neutral two-leg trade. Enter at the next hourly open after the completed-hour log-price-ratio z-score reaches 1.5–3.0; exit on mean reversion or after 6–48 hours.
- Universe: ADA, ATOM, FIL, XLM, AAVE, ETC; 15 pairs.
- Grid: 576 parameter sets per pair across 72/168/336/720-hour windows, three entry thresholds, three exits, four holds, and 1–3x gross leverage. Each chronological third nominated a rule, then that frozen rule was tested on all thirds.
- Result: 0 of 15 pairs produced a rule profitable in all three thirds under the stated risk gates.
- Numerically highest full-period rule: ATOM/AAVE, 336-hour window, z=3.0 entry, z=0.5 exit, 6-hour cap, 3x gross; 244 trades, 53.28% wins, $100 -> $178.96 (+78.96%), MDD -65.65%.
- Segment returns: +304.37%, -37.25%, -29.47%. Double-cost result: -35.83%, MDD -81.67%.
- Decision: reject as A/B addition and reject as C plan. The apparent full-period gain is regime-dependent and cost-fragile.

Evidence: `research/results/pair_reversion_stage87/results.json`

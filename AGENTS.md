# A/B trading plan invariants

Before ANY trading/research/UI/deployment work, start at `strategy/work_map/README.md`, select the relevant A/B/controller/research map, then read `strategy/PLANS.md`, `strategy/mdd30_standard.json`, and `strategy/plan_b_standard.json` in full.

- A is the existing `answer_mdd30` system. Current A is `mdd30_5x_c_controller_stage184_v1`; current B is `b_regime_guard_stage112` / `b_regime_guard_stage112_v1`. Never infer one plan's settings from the other.
- Read `strategy/plan_b_combination_standard.json`, `strategy/B_STAGE112_APPROVED_20260910.md`, and `strategy/B_STAGE26_APPROVED_20260831.md` before B work. Stage112 is the current deployed B standard; Stage26 is required history for the core/supplement execution invariants, not the current runtime ID. Owner-enabled switches stay ON. Financial notifications to chat 6818439075 were explicitly approved on 2026-08-31. Never bypass order preflight. Stage16 is an archived research baseline, not the current B runtime ID.
- Preserve research opportunity cooldowns independently of fills: supplementary holding is 1h but selected signal boundaries must be >=2h apart. A and new B can both trade ETH through completely separate accounts; symbol disjointness is not an isolation invariant.
- The words "종목별 A+B" inside A's model describe internal components, NOT the platform B plan.
- B Stage14/15 headline returns were withdrawn. Never restore their 5.75 multiplier, 20.7x exposure or claimed returns as active B settings.
- The user adopted corrected Stage16, including its return below the previous research goal. Adoption is not proof of live validation.
- B reserves available margin, clips simultaneous requests proportionately, and fixes quantity at entry. A keeps its own existing sizing.
- B live performance baseline is $650, explicitly confirmed by the user on 2026-09-08 after increasing it from the original $150. Historical research remains on its original $100 basis. Public B trade history was explicitly approved on 2026-08-30; never expose secrets/control endpoints with it.
- Keep credentials, signals, trades, control sessions, IDs, notifications and state isolated. Never fall back to A credentials/tables for B.
- Telegram receive/delivery repair: read `strategy/TELEGRAM_DELIVERY_REPAIR_20260831.md`; preserve authenticated webhook and per-trade delivery markers. Do not restore global ID/time-only notification eligibility or claim exactly-once delivery.
- Read `strategy/SECURITY_HISTORY_REPAIR_20260831.md` for scoped dashboard sessions, DB login limits, complete A history pagination, and the unresolved three-source news HTTP403 blocker. Never restore unscoped sessions or label realized-basis funds as actual collateral.
- Do not activate or deploy live trading merely because a strategy was adopted. Check live_ready and report unresolved execution work honestly.
- Before handoff run `research/scripts/audit_plan_separation.py`, `research/scripts/test_reserved_margin_stage16.py`, and the Node sizing tests. An A invariant change needs explicit user authorization and review.
- Never claim perpetual memory. These files are the persistent source of truth; maintain them with user-approved changes.

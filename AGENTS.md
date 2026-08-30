# A/B trading plan invariants

Before ANY trading/research/UI/deployment work read `strategy/PLANS.md`, `strategy/mdd30_standard.json`, and `strategy/plan_b_standard.json` in full.

- A is the existing `answer_mdd30` system. B is `b_reserved_margin_stage16`. Never infer one plan's settings from the other.
- The words "종목별 A+B" inside A's model describe internal components, NOT the platform B plan.
- B Stage14/15 headline returns were withdrawn. Never restore their 5.75 multiplier, 20.7x exposure or claimed returns as active B settings.
- The user adopted corrected Stage16, including its return below the previous research goal. Adoption is not proof of live validation.
- B reserves available margin, clips simultaneous requests proportionately, and fixes quantity at entry. A keeps its own existing sizing.
- Keep credentials, signals, trades, control sessions, IDs, notifications and state isolated. Never fall back to A credentials/tables for B.
- Do not activate or deploy live trading merely because a strategy was adopted. Check live_ready and report unresolved execution work honestly.
- Before handoff run `research/scripts/audit_plan_separation.py`, `research/scripts/test_reserved_margin_stage16.py`, and the Node sizing tests. An A invariant change needs explicit user authorization and review.
- Never claim perpetual memory. These files are the persistent source of truth; maintain them with user-approved changes.

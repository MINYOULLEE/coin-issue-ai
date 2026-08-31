# A/B trading plan invariants

Before ANY trading/research/UI/deployment work read `strategy/PLANS.md`, `strategy/mdd30_standard.json`, and `strategy/plan_b_standard.json` in full.

- A is the existing `answer_mdd30` system. Current B is `b_core_sparse_stage26` (Stage16 core + ALGO/ETH/VET). Never infer one plan's settings from the other.
- Read `strategy/plan_b_combination_standard.json` and `strategy/B_STAGE26_ROLLOUT_20260831.md` before B work. Stage26 core functions and DB strategy ID are deployed; owner-enabled switches stay ON. ALGO/ETH/VET were still isolated 20x in the latest account check, so their 3x entry preflight must not be bypassed. Telegram upgrade deployment is blocked pending explicit approval for financial data to chat 6818439075. Stage16 is an archived research baseline, not the current B runtime ID.
- Preserve research opportunity cooldowns independently of fills: supplementary holding is 1h but selected signal boundaries must be >=2h apart. A and new B can both trade ETH through completely separate accounts; symbol disjointness is not an isolation invariant.
- The words "종목별 A+B" inside A's model describe internal components, NOT the platform B plan.
- B Stage14/15 headline returns were withdrawn. Never restore their 5.75 multiplier, 20.7x exposure or claimed returns as active B settings.
- The user adopted corrected Stage16, including its return below the previous research goal. Adoption is not proof of live validation.
- B reserves available margin, clips simultaneous requests proportionately, and fixes quantity at entry. A keeps its own existing sizing.
- B live performance starts from $150, explicitly confirmed by the user. Historical research remains on its original $100 basis. Public B trade history was explicitly approved on 2026-08-30; never expose secrets/control endpoints with it.
- Keep credentials, signals, trades, control sessions, IDs, notifications and state isolated. Never fall back to A credentials/tables for B.
- Do not activate or deploy live trading merely because a strategy was adopted. Check live_ready and report unresolved execution work honestly.
- Before handoff run `research/scripts/audit_plan_separation.py`, `research/scripts/test_reserved_margin_stage16.py`, and the Node sizing tests. An A invariant change needs explicit user authorization and review.
- Never claim perpetual memory. These files are the persistent source of truth; maintain them with user-approved changes.

# A/B security and history repair — 2026-08-31

User authorized error repairs. Trading strategies, sizing, live switches and schedules are unchanged.

## Deployed

- A account endpoint v45 and B account endpoint v16: versioned, plan-scoped HMAC sessions. Legacy unscoped sessions rejected; owner must log into the control UI again. This does not disable automated trading.
- Shared database login limiter: five attempts (including successful attempts) per plan and client IP in fifteen minutes. Hashed client identifiers only; database failure denies login. Service-only table/RPC, RLS enabled.
- A public web history and Telegram history: removed the 2,000-row truncation, fetch all pages, reject failed/inconsistent pagination instead of showing a partial successful total.
- Telegram webhook v20: A history labels $100 plus realized net PnL as realized-basis funds, in USDT, excluding deposits/withdrawals and unrealized PnL. Actual collateral remains in account status.

## Verification

- Live read-only session matrix: A→A 200, A→B 401, B→A 401, B→B 200 (HTTP request IDs 22287–22290). No orders or control changes performed.
- Public A/B history HTTP 200; unauthenticated controls HTTP 401.
- A database closed history: 45 records, net 62.394305 USDT; public aggregate matches. B closed history: zero.
- SQL rollback tests: five allowed, sixth blocked, A/B buckets independent, expired bucket reset; anonymous/authenticated RPC execution denied. Test fixtures rolled back.
- Offline pagination fixture: 2,507 rows including a simulated 200-row server cap; session expiry, tampering, legacy tokens and cross-plan tokens covered by regression tests.
- Final regression: 89 Node tests passed, two Stage16 sizing tests and three adoption-artifact tests passed; all 52 frozen files passed separation audit. Downloaded deployed sources and dependencies match the local repair.
- Final live state read: A enabled=true/test_mode=false and B enabled=true/test_mode=false.
- Supabase security advisor: no WARN/ERROR findings; service-only tables have informational RLS-without-policy notices intentionally denying client access. Reference: https://supabase.com/docs/guides/database/database-linter?lint=0008_rls_enabled_no_policy

## Unresolved — do not report all errors fixed

Coinbase Blog, CFTC Press and CFTC Speeches still return HTTP 403 from the Supabase Edge collection environment. Official CFTC HTML fallbacks are also blocked. Eight other sources continue to collect; partial-failure monitoring stays enabled. Coinbase Status is not a substitute for Coinbase Blog. No unverified proxy, unrelated feed substitution or monitoring suppression was introduced.

An approved collection environment that can access the official sources, or an officially supported equivalent source, is still needed. This repair does not certify future live performance or eliminate exchange/platform outages.

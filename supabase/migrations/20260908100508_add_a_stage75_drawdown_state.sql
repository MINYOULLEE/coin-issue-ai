alter table public.real_trading_state
  add column if not exists a_equity_peak_usd numeric,
  add column if not exists a_drawdown_guard_active boolean not null default false,
  add column if not exists a_last_drawdown_pct numeric;

comment on column public.real_trading_state.a_equity_peak_usd is
  'A Stage75 actual BingX equity high-water mark';
comment on column public.real_trading_state.a_drawdown_guard_active is
  'A Stage75 hysteresis guard: 35% activate, 17.5% recover';

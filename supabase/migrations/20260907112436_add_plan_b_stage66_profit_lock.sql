alter table public.plan_b_real_trades
  add column if not exists exit_reason text,
  add column if not exists profit_lock_policy text,
  add column if not exists profit_lock_trigger_pct numeric,
  add column if not exists profit_lock_keep_fraction numeric,
  add column if not exists profit_lock_armed_at timestamptz,
  add column if not exists profit_lock_peak_pct numeric,
  add column if not exists profit_lock_floor_price numeric,
  add column if not exists profit_lock_last_candle_at timestamptz;

alter table public.plan_b_real_trades
  drop constraint if exists plan_b_real_trades_exit_reason_check;

alter table public.plan_b_real_trades
  add constraint plan_b_real_trades_exit_reason_check
  check (exit_reason is null or exit_reason in ('scheduled_time', 'profit_lock'));

comment on column public.plan_b_real_trades.profit_lock_floor_price is
  'Stage66 server-managed protective floor; never supplied by public clients.';

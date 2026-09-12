begin;

alter table public.managed_bingx_accounts
  add column if not exists live_enabled_at timestamptz,
  add column if not exists a_equity_peak_usdt numeric(24,8),
  add column if not exists a_drawdown_guard_active boolean not null default false;

alter table public.managed_bingx_trades
  add column if not exists signal_id bigint,
  add column if not exists bingx_order_id text,
  add column if not exists client_order_id text,
  add column if not exists stop_order_id text,
  add column if not exists stop_price numeric(32,12),
  add column if not exists target_price numeric(32,12),
  add column if not exists close_reason text,
  add column if not exists last_error text;

create unique index if not exists managed_bingx_trades_account_signal_uidx
  on public.managed_bingx_trades(account_id, signal_id)
  where signal_id is not null;

create index if not exists managed_bingx_accounts_live_idx
  on public.managed_bingx_accounts(assigned_plan, live_enabled)
  where live_enabled;

commit;

create table if not exists public.coin_snapshots (
  id text primary key,
  payload jsonb not null default '{}'::jsonb,
  updated_at timestamptz not null default now()
);
alter table public.coin_snapshots enable row level security;
drop policy if exists "public can read live snapshot" on public.coin_snapshots;
create policy "public can read live snapshot" on public.coin_snapshots for select to anon using (id = 'live');
revoke insert, update, delete on public.coin_snapshots from anon;
grant select on public.coin_snapshots to anon;


-- 24-hour recommendation lifecycle.
-- One coin can have only one open recommendation. Entry/target/invalidation
-- values are locked at creation and the cloud collector only changes status.
create table if not exists public.trade_signals (
  id bigint generated always as identity primary key,
  symbol text not null check (symbol in ('BTC','ETH','XRP','SOL','BNB')),
  side text not null check (side in ('long','short')),
  status text not null default 'active' check (status in ('active','weakening','success','failure','neutral','expired','invalidated')),
  entry_price numeric not null check (entry_price > 0),
  invalidation_price numeric not null check (invalidation_price > 0),
  target_price numeric not null check (target_price > 0),
  confidence smallint not null check (confidence between 0 and 100),
  reasons jsonb not null default '[]'::jsonb,
  entry_metrics jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  expires_at timestamptz not null,
  updated_at timestamptz not null default now(),
  closed_at timestamptz,
  exit_price numeric,
  result_pct numeric,
  close_reason text
);
create unique index if not exists trade_signals_one_active_per_symbol
  on public.trade_signals(symbol)
  where status in ('active','weakening');
create index if not exists trade_signals_recent_idx
  on public.trade_signals(created_at desc);
alter table public.trade_signals enable row level security;
revoke all on public.trade_signals from anon, authenticated;

drop policy if exists "deny direct signal access" on public.trade_signals;
create policy "deny direct signal access"
  on public.trade_signals for all
  to anon, authenticated
  using (false)
  with check (false);


-- Separate 24-hour trend signals from 1-minute tactical long/short signals.
alter table public.trade_signals add column if not exists signal_type text not null default 'swing', add column if not exists horizon_minutes integer not null default 1440;
alter table public.trade_signals drop constraint if exists trade_signals_signal_type_check;
alter table public.trade_signals add constraint trade_signals_signal_type_check check (signal_type in ('swing','tactical'));
alter table public.trade_signals drop constraint if exists trade_signals_horizon_minutes_check;
alter table public.trade_signals add constraint trade_signals_horizon_minutes_check check (horizon_minutes between 1 and 10080);
drop index if exists public.trade_signals_one_open_per_symbol;
drop index if exists public.trade_signals_one_active_per_symbol;
create unique index if not exists trade_signals_one_open_per_symbol_type on public.trade_signals(symbol, signal_type) where status in ('active','weakening');


-- $1,000 risk-sized leveraged paper-trading performance.
alter table public.trade_signals
 add column if not exists account_equity_usd numeric not null default 1000,
 add column if not exists margin_usd numeric,
 add column if not exists leverage integer,
 add column if not exists notional_usd numeric,
 add column if not exists fee_usd numeric,
 add column if not exists net_pnl_usd numeric,
 add column if not exists leveraged_return_pct numeric;
alter table public.trade_signals drop constraint if exists trade_signals_leverage_check;
alter table public.trade_signals add constraint trade_signals_leverage_check check (leverage is null or leverage between 1 and 5);
alter table public.trade_signals drop constraint if exists trade_signals_margin_check;
alter table public.trade_signals add constraint trade_signals_margin_check check (margin_usd is null or margin_usd >= 0);

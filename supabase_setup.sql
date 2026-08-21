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
  status text not null default 'active' check (status in ('active','weakening','expired','invalidated')),
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

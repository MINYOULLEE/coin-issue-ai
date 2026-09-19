create table if not exists public.plan_b_bingx_trade_history (
  external_id text primary key,
  position_id text,
  symbol text not null,
  side text not null check (side in ('long','short')),
  status text not null check (status in ('open','closed','stale')),
  entry_price numeric,
  close_price numeric,
  quantity numeric,
  margin_usd numeric,
  leverage integer,
  realized_pnl_usd numeric,
  unrealized_pnl_usd numeric,
  fee_usd numeric,
  opened_at timestamptz,
  closed_at timestamptz,
  raw jsonb not null default '{}'::jsonb,
  synced_at timestamptz not null default now(),
  control_marker smallint not null default 1 check (control_marker in (1,2))
);

alter table public.plan_b_bingx_trade_history enable row level security;
revoke all on table public.plan_b_bingx_trade_history from anon, authenticated;
comment on table public.plan_b_bingx_trade_history is 'Service-only BingX exchange ledger snapshot for the isolated Plan B account.';
comment on column public.plan_b_bingx_trade_history.control_marker is '1=automatic only, 2=owner manual entry, resize, or close occurred.';
create index if not exists plan_b_bingx_trade_history_opened_idx on public.plan_b_bingx_trade_history(opened_at desc);
create index if not exists plan_b_bingx_trade_history_status_idx on public.plan_b_bingx_trade_history(status);

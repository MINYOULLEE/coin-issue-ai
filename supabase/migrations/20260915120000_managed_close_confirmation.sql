begin;
-- Durable attempt identity and manual remainder must survive a timeout/restart.
alter table public.managed_bingx_trades
  add column if not exists close_context jsonb;
comment on column public.managed_bingx_trades.close_context is
  'Account-scoped close attempt; persist before submission and reconcile before retry. No credentials.';
commit;

begin;

alter table public.managed_bingx_accounts
  add column if not exists a_strategy_version text,
  add column if not exists a_strategy_aligned_at timestamptz,
  add column if not exists a_last_rebalance_closed_ms bigint;

comment on column public.managed_bingx_accounts.a_strategy_version is
  'Last A runtime standard successfully reconciled against this managed BingX account.';
comment on column public.managed_bingx_accounts.a_strategy_aligned_at is
  'Last successful exchange-side A leverage/runtime reconciliation timestamp.';
comment on column public.managed_bingx_accounts.a_last_rebalance_closed_ms is
  'Latest completed A daily decision candle already applied to this managed account.';

commit;

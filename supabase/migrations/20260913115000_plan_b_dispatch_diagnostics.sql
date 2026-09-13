alter table public.plan_b_signals
  add column if not exists dispatch_block_reason text,
  add column if not exists dispatch_checked_at timestamptz;

comment on column public.plan_b_signals.dispatch_block_reason is
  'Latest server-side reason an otherwise-live B signal was not reserved. Diagnostic only; never bypasses preflight.';

comment on column public.plan_b_signals.dispatch_checked_at is
  'Last B executor eligibility/preflight diagnostic timestamp.';

update public.plan_b_signals
set status = 'expired',
    dispatch_block_reason = 'expired_before_dispatch_diagnostics',
    dispatch_checked_at = clock_timestamp(),
    updated_at = clock_timestamp()
where status = 'active'
  and dispatched_at is null
  and entry_deadline <= clock_timestamp();

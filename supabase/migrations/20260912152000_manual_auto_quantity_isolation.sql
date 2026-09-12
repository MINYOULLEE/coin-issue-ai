begin;

alter table public.plan_b_execution_intents
  add column if not exists manual_remainder_qty numeric not null default 0
  check (manual_remainder_qty >= 0);

comment on column public.plan_b_execution_intents.manual_remainder_qty is
  'Exchange same-side quantity not owned by the automatic trade; never close this remainder.';

commit;

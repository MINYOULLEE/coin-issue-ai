begin;
alter table public.managed_bingx_accounts
  add column if not exists desired_strategy_version text,
  add column if not exists applied_strategy_version text,
  add column if not exists strategy_version_synced_at timestamptz;
update public.managed_bingx_accounts set
 desired_strategy_version=case assigned_plan when 'A' then 'mdd30_5x_c_controller_stage184_v1' when 'B' then 'b_regime_guard_stage112_v1' end,
 applied_strategy_version=case when assigned_plan='A' and a_strategy_version='mdd30_5x_c_controller_stage184_v1' then 'mdd30_5x_c_controller_stage184_v1' else applied_strategy_version end,
 strategy_version_synced_at=case when assigned_plan='A' and a_strategy_version='mdd30_5x_c_controller_stage184_v1' then coalesce(a_strategy_aligned_at,now()) else strategy_version_synced_at end;
comment on column public.managed_bingx_accounts.desired_strategy_version is 'Centrally approved version for assigned_plan; never user supplied.';
comment on column public.managed_bingx_accounts.applied_strategy_version is 'Version fully reconciled on this account.';
commit;

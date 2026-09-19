begin;
alter table public.bingx_trade_history add column if not exists control_marker smallint not null default 1 check (control_marker in (1,2));
alter table public.plan_b_real_trades add column if not exists control_marker smallint not null default 1 check (control_marker in (1,2));
alter table public.managed_bingx_trades add column if not exists control_marker smallint not null default 1 check (control_marker in (1,2));
comment on column public.bingx_trade_history.control_marker is '1=automatic only, 2=owner manual entry, resize, or close occurred.';
comment on column public.plan_b_real_trades.control_marker is '1=automatic only, 2=owner manual entry, resize, or close occurred.';
comment on column public.managed_bingx_trades.control_marker is '1=automatic copier only, 2=manual intervention occurred.';
commit;

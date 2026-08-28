-- system_errors is internal operational telemetry. It must never be exposed
-- through the public Data API roles.
alter table public.system_errors enable row level security;

revoke all privileges on table public.system_errors from anon, authenticated;
revoke all privileges on sequence public.system_errors_id_seq from anon, authenticated;

-- No anon/authenticated policy is intentional. Edge Functions use the
-- service-role credential and continue to record and inspect errors.

-- Daily-rebalance strategies intentionally have no fixed exchange stop or
-- take-profit. Nullable columns let the database represent that truth instead
-- of storing the entry price as a misleading placeholder.
alter table public.real_trades alter column stop_price drop not null;
alter table public.real_trades alter column target_price drop not null;

-- Serialize the final live-order admission decision in Postgres. A short-lived
-- reservation closes the read-then-order race between concurrent Edge
-- Function invocations and expires automatically if an invocation crashes.
create table if not exists public.trade_execution_reservations (
  signal_id bigint primary key references public.trade_signals(id) on delete cascade,
  symbol text not null,
  side text not null check (side in ('long','short')),
  created_at timestamptz not null default now()
);
alter table public.trade_execution_reservations enable row level security;
revoke all privileges on table public.trade_execution_reservations from anon, authenticated, public;

create or replace function public.reserve_real_trade_slot(
  p_signal_id bigint,
  p_symbol text,
  p_side text,
  p_max_concurrent integer,
  p_max_same_direction integer
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
  active_total integer;
  active_same integer;
begin
  if coalesce(current_setting('request.jwt.claims', true)::jsonb ->> 'role', '') <> 'service_role' then
    raise exception 'service_role required';
  end if;

  perform pg_advisory_xact_lock(hashtext('coin_issue_ai_real_trade_slot'));
  delete from public.trade_execution_reservations
  where created_at < now() - interval '10 minutes';

  if exists (
    select 1 from public.real_trades where signal_id = p_signal_id
    union all
    select 1 from public.trade_execution_reservations where signal_id = p_signal_id
  ) then
    return jsonb_build_object('reserved', false, 'reason', 'already_traded_or_reserved');
  end if;

  select
    (select count(*) from public.real_trades where status = 'open')
      + (select count(*) from public.trade_execution_reservations),
    (select count(*) from public.real_trades where status = 'open' and side = p_side)
      + (select count(*) from public.trade_execution_reservations where side = p_side)
  into active_total, active_same;

  if active_total >= p_max_concurrent then
    return jsonb_build_object('reserved', false, 'reason', 'max_concurrent_positions');
  end if;
  if active_same >= p_max_same_direction then
    return jsonb_build_object('reserved', false, 'reason', 'max_same_direction_positions');
  end if;
  if exists (
    select 1 from public.real_trades where status = 'open' and symbol = p_symbol and side = p_side
  ) or exists (
    select 1 from public.trade_execution_reservations where symbol = p_symbol and side = p_side
  ) then
    return jsonb_build_object('reserved', false, 'reason', 'same_symbol_side_exists');
  end if;

  insert into public.trade_execution_reservations(signal_id, symbol, side)
  values (p_signal_id, p_symbol, p_side);
  return jsonb_build_object('reserved', true);
end;
$$;

revoke all on function public.reserve_real_trade_slot(bigint,text,text,integer,integer) from public, anon, authenticated;
grant execute on function public.reserve_real_trade_slot(bigint,text,text,integer,integer) to service_role;

-- This maintenance function is invoked by the database cron job, not by
-- browser clients. Do not expose its SECURITY DEFINER privileges over RPC.
revoke all on function public.capture_recent_http_errors() from public, anon, authenticated;

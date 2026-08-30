-- 2026-08-31 repairs 1-5. Additive; no trading switch or scheduler change.
begin;
alter table public.trade_execution_reservations add column if not exists request_payload jsonb;
alter table public.trade_execution_reservations add column if not exists execution_status text;
alter table public.trade_execution_reservations add column if not exists last_error text;
alter table public.trade_execution_reservations add column if not exists updated_at timestamptz not null default now();
alter table public.plan_b_real_trades add column if not exists telegram_close_notified_at timestamptz;
create table if not exists public.plan_b_runtime_health(id text primary key, payload jsonb not null, updated_at timestamptz not null default now());
alter table public.plan_b_runtime_health enable row level security;
revoke all on public.plan_b_runtime_health from public,anon,authenticated;
grant all on public.plan_b_runtime_health to service_role;
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
  where created_at < now() - interval '10 minutes' and request_payload is null;

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


commit;

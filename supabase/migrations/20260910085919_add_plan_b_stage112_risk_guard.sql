alter table public.plan_b_trading_state
  add column if not exists risk_equity_peak_usdt numeric,
  add column if not exists risk_pause_until timestamptz,
  add column if not exists risk_last_equity_usdt numeric,
  add column if not exists risk_updated_at timestamptz;

create or replace function public.plan_b_update_risk_guard(p_equity numeric, p_now timestamptz)
returns jsonb
language plpgsql
set search_path = public
as $$
declare
  s public.plan_b_trading_state%rowtype;
  peak numeric;
  pause_until timestamptz;
  dd numeric;
begin
  if p_equity is null or p_equity <= 0 or p_now is null then
    raise exception 'invalid B risk snapshot';
  end if;
  select * into s from public.plan_b_trading_state where id='singleton' for update;
  if not found then raise exception 'B state missing'; end if;

  pause_until := s.risk_pause_until;
  if pause_until is not null and p_now >= pause_until then
    pause_until := null;
    peak := p_equity;
  else
    peak := greatest(coalesce(s.risk_equity_peak_usdt,p_equity),p_equity);
  end if;
  dd := p_equity / peak - 1;
  if pause_until is null and dd <= -0.25 then
    pause_until := p_now + interval '168 hours';
  end if;

  update public.plan_b_trading_state
     set risk_equity_peak_usdt=peak,risk_pause_until=pause_until,
         risk_last_equity_usdt=p_equity,risk_updated_at=p_now
   where id='singleton';
  return jsonb_build_object('entry_allowed',pause_until is null,'equity',p_equity,
    'peak',peak,'drawdown_fraction',dd,'pause_until',pause_until);
end;
$$;

revoke all on function public.plan_b_update_risk_guard(numeric,timestamptz) from public, anon, authenticated;
grant execute on function public.plan_b_update_risk_guard(numeric,timestamptz) to service_role;

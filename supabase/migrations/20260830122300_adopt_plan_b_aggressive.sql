-- UNAPPLIED local preparation; Stage16 only. A schema/state untouched.
alter table public.plan_b_signals drop constraint if exists plan_b_signals_symbol_check;
alter table public.plan_b_signals
  add constraint plan_b_signals_symbol_check check (symbol in ('AVAX','ICP','BCH','DOGE','UNI'));

alter table public.plan_b_signals
  add column if not exists strategy_id text not null default 'b_reserved_margin_stage16',
  add column if not exists strategy_params jsonb not null default '{}'::jsonb,
  add column if not exists entry_deadline timestamptz,
  add column if not exists dispatched_at timestamptz;

alter table public.plan_b_trading_state
  add column if not exists profile text not null default 'aggressive',
  add column if not exists portfolio_scale numeric not null default 1,
  add column if not exists max_gross_exposure numeric,
  add column if not exists max_closed_trade_mdd_pct numeric not null default 70,
  add column if not exists validation_status text not null default 'stage16_user_adopted_not_live';

alter table public.plan_b_trading_state
  add column if not exists sizing_mode text not null default 'reserved_margin_fixed_entry_quantity',
  add column if not exists target_margin_fraction numeric not null default 1.15,
  add column if not exists cash_buffer_fraction numeric not null default 0.05;

update public.plan_b_trading_state
set strategy_id='b_reserved_margin_stage16',
    profile='aggressive', portfolio_scale=1, max_gross_exposure=null,
    max_closed_trade_mdd_pct=70, validation_status='stage16_user_adopted_not_live',
    enabled=false, test_mode=true, updated_at=now()
where id='singleton';

create index if not exists plan_b_signals_active_symbol_idx
  on public.plan_b_signals(symbol, status, confirmed_at desc);
create index if not exists plan_b_real_trades_status_idx
  on public.plan_b_real_trades(status, created_at desc);

-- Scheduler activation is deliberately deferred until atomic B reservation/executor validation.

-- Global statistics, independent of the currently displayed history page.
create or replace function public.plan_b_history_stats()
returns jsonb language sql stable security invoker set search_path = '' as $$
 select jsonb_build_object(
 'closed',count(*),'wins',count(*) filter(where net_pnl_usd>0),
 'losses',count(*) filter(where net_pnl_usd<0),
 'win_rate',coalesce(100.0*count(*) filter(where net_pnl_usd>0)/nullif(count(*),0),0),
 'total_pnl_usd',coalesce(sum(net_pnl_usd),0),'total_fee_usd',coalesce(sum(abs(fee_usd)),0),
 'current_balance_usd',null,'balance_source','not_inferred_from_research_seed')
 from public.plan_b_real_trades where status='closed';
$$;
revoke all on function public.plan_b_history_stats() from public,anon,authenticated;
grant execute on function public.plan_b_history_stats() to service_role;

-- Paper execution preparation uses its own ledger, never the real trade history.
create table if not exists public.plan_b_paper_reservations (
 client_order_id text primary key check(client_order_id like 'pb16-%'),
 symbol text not null check(symbol in ('AVAX','ICP','BCH','DOGE','UNI')),
 reservation_usd numeric not null check(reservation_usd>0),
 quantity numeric not null check(quantity>0),
 status text not null default 'reserved' check(status in ('reserved','claimed','unknown','filled','partially_filled','expired','rejected','closed')),
 fill_quantity numeric, fill_price numeric,
 released boolean not null default false,
 created_at timestamptz not null default now(), updated_at timestamptz not null default now()
);
alter table public.plan_b_paper_reservations enable row level security;
revoke all on public.plan_b_paper_reservations from public,anon,authenticated;
grant all on public.plan_b_paper_reservations to service_role;

create or replace function public.plan_b_paper_reserve(p_orders jsonb,p_equity numeric,p_balance numeric)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare held numeric; demand numeric; available numeric; item jsonb;
begin
 perform pg_advisory_xact_lock(160830);
 if p_equity is null or p_balance is null or p_equity<=0 or p_balance<=0
   or p_equity::text in ('NaN','Infinity','-Infinity') or p_balance::text in ('NaN','Infinity','-Infinity') then
   raise exception 'invalid paper account';
 end if;
 if jsonb_typeof(p_orders) is distinct from 'array' or jsonb_array_length(p_orders)=0 then raise exception 'empty batch'; end if;
 if (select count(*)<>count(distinct value->>'symbol') from jsonb_array_elements(p_orders)) then raise exception 'duplicate symbol'; end if;
 select coalesce(sum(reservation_usd),0) into held from public.plan_b_paper_reservations where not released;
 available:=greatest(0,least(p_balance-held,p_equity-held)-p_equity*0.05);
 select sum((value->>'reservation_usd')::numeric) into demand from jsonb_array_elements(p_orders);
 if demand is null or demand::text in ('NaN','Infinity','-Infinity') or demand>available then raise exception 'paper margin exhausted'; end if;
 for item in select value from jsonb_array_elements(p_orders) loop
  if (item->>'reservation_usd')::numeric<=0 or (item->>'quantity')::numeric<=0
    or (item->>'quantity')::numeric::text in ('NaN','Infinity','-Infinity') then raise exception 'invalid quantity/reserve'; end if;
  if exists(select 1 from public.plan_b_paper_reservations where symbol=item->>'symbol' and not released) then raise exception 'symbol already reserved'; end if;
  insert into public.plan_b_paper_reservations(client_order_id,symbol,reservation_usd,quantity)
   values(item->>'client_order_id',item->>'symbol',(item->>'reservation_usd')::numeric,(item->>'quantity')::numeric);
 end loop;
 return jsonb_build_object('reserved',demand,'available_before',available,'mode','paper');
end; $$;
revoke all on function public.plan_b_paper_reserve(jsonb,numeric,numeric) from public,anon,authenticated;
grant execute on function public.plan_b_paper_reserve(jsonb,numeric,numeric) to service_role;

create or replace function public.plan_b_paper_claim(p_id text)
returns boolean language plpgsql security invoker set search_path='' as $$
declare n integer;
begin
 update public.plan_b_paper_reservations set status='claimed',updated_at=now() where client_order_id=p_id and status='reserved' and not released;
 get diagnostics n = row_count;
 return n=1;
end; $$;
revoke all on function public.plan_b_paper_claim(text) from public,anon,authenticated;
grant execute on function public.plan_b_paper_claim(text) to service_role;

-- User-approved execution safety repair; does not change strategy thresholds or account switches.
begin;
alter table public.plan_b_execution_intents add column if not exists close_attempt integer not null default 0;
alter table public.plan_b_execution_intents add column if not exists close_client_order_id text;
alter table public.plan_b_execution_intents add column if not exists close_quantity numeric;
-- Pending exchange settlement is not a zero-profit closed trade.
create or replace function public.plan_b_history_stats() returns jsonb language sql stable security invoker set search_path='' as $$
 select jsonb_build_object('closed',count(*),'wins',count(*) filter(where net_pnl_usd>0),'losses',count(*) filter(where net_pnl_usd<0),
 'win_rate',coalesce(100.0*count(*) filter(where net_pnl_usd>0)/nullif(count(*),0),0),
 'total_pnl_usd',coalesce(sum(net_pnl_usd),0),'total_fee_usd',coalesce(sum(abs(fee_usd)),0),
 'starting_capital_usd',(select starting_capital_usd from public.plan_b_trading_state where id='singleton'),
 'realized_equity_usd',(select starting_capital_usd from public.plan_b_trading_state where id='singleton')+coalesce(sum(net_pnl_usd),0),
 'current_balance_usd',null,'balance_source','starting_capital_plus_settled_pnl_not_exchange_balance')
 from public.plan_b_real_trades where status='closed' and net_pnl_usd is not null and bingx_order_id is not null;
$$;
revoke all on function public.plan_b_history_stats() from public,anon,authenticated;
grant execute on function public.plan_b_history_stats() to service_role;
commit;

begin;

-- Preserve owner ON/LIVE. Expire only an already-dead, undispatched signal.
update public.plan_b_signals set status='expired',updated_at=clock_timestamp()
where status='active' and dispatched_at is null and entry_deadline<=clock_timestamp();

do $$ begin
 if exists(select 1 from public.plan_b_signals where status='active')
 or exists(select 1 from public.plan_b_real_trades where status='open')
 or exists(select 1 from public.plan_b_execution_intents where status in ('reserved','submitted','unknown','partial','open','closing'))
 then raise exception 'Stage93 transition requires no active B signals, trades, or intents'; end if;
end; $$;

alter table public.plan_b_signals drop constraint if exists plan_b_signals_symbol_check;
alter table public.plan_b_signals add constraint plan_b_signals_symbol_check
 check(symbol in ('AVAX','ICP','BCH','DOGE','UNI','ALGO','ETH','VET','LINK','DOT','LTC','BNB','ADA'));
alter table public.plan_b_execution_intents drop constraint if exists plan_b_execution_intents_symbol_check;
alter table public.plan_b_execution_intents add constraint plan_b_execution_intents_symbol_check
 check(symbol in ('AVAX','ICP','BCH','DOGE','UNI','ALGO','ETH','VET','LINK','DOT','LTC','BNB','ADA'));
alter table public.plan_b_execution_intents drop constraint if exists plan_b_execution_intents_client_order_id_check;
alter table public.plan_b_execution_intents add constraint plan_b_execution_intents_client_order_id_check
 check(client_order_id ~ '^pb(16|26|35|45|66|93)-[0-9]+$');

insert into public.plan_b_rules(symbol,trade_group,leverage,hold_hours,cooldown_hours,target_fraction)
values('ADA','supplement',3,7,8,.25)
on conflict(symbol) do update set trade_group=excluded.trade_group,leverage=excluded.leverage,
 hold_hours=excluded.hold_hours,cooldown_hours=excluded.cooldown_hours,target_fraction=excluded.target_fraction;

update public.plan_b_opportunity_state set payload=jsonb_set(
 jsonb_set(payload,'{version}','"b_algo_ada_stage93_v1"'::jsonb),
 '{nextEligibleAt}',coalesce(payload->'nextEligibleAt','{}'::jsonb)||jsonb_build_object(
 'ADA',(payload->>'lastConfirmedAt')::bigint)),updated_at=clock_timestamp()
where id='singleton' and payload->>'version'='b_profit_lock_stage66_v1';

update public.plan_b_trading_state set strategy_id='b_algo_ada_stage93',
 validation_status='stage93_history_and_futures_minute_verified_pending_natural_bingx_fill',updated_at=clock_timestamp()
where id='singleton' and strategy_id='b_profit_lock_stage66';

create or replace function public.plan_b_claim_intent(p_id text)
returns boolean language plpgsql set search_path='' as $$
declare n integer;
begin
 perform 1 from public.plan_b_trading_state
 where id='singleton' and enabled and not test_mode and strategy_id='b_algo_ada_stage93' for update;
 if not found then return false; end if;
 update public.plan_b_execution_intents i set status='submitted',updated_at=now()
 from public.plan_b_signals s
 where i.signal_id=s.id and i.client_order_id=p_id and i.status='reserved'
   and s.entry_deadline>clock_timestamp() and s.strategy_id='b_algo_ada_stage93'
   and s.confirmed_at<=clock_timestamp() and clock_timestamp()-s.confirmed_at<interval '5 minutes';
 get diagnostics n=row_count;return n=1;
end; $$;

-- Move the reviewed atomic functions to the new exact ID/version/prefix and 13 decisions.
do $$ declare d text; begin
 select pg_get_functiondef('public.plan_b_publish_opportunities(bigint,jsonb)'::regprocedure) into d;
 d:=replace(replace(replace(replace(replace(d,
   'b_profit_lock_stage66_v1','b_algo_ada_stage93_v1'),
   'b_profit_lock_stage66','b_algo_ada_stage93'),
   'pb66:','pb93:'),'<>12','<>13'),'all twelve decisions required','all thirteen decisions required');
 execute d;
 select pg_get_functiondef('public.plan_b_reserve_intents(jsonb,numeric,numeric,numeric,timestamp with time zone)'::regprocedure) into d;
 d:=replace(replace(replace(d,'b_profit_lock_stage66_v1','b_algo_ada_stage93_v1'),
   'b_profit_lock_stage66','b_algo_ada_stage93'),'pb66-','pb93-');
 execute d;
end; $$;

commit;

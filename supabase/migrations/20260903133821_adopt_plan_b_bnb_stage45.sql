begin;

-- Clear only already-expired, undispatched signals; preserve every live switch.
update public.plan_b_signals set status='expired',updated_at=clock_timestamp()
where status='active' and dispatched_at is null and entry_deadline<=clock_timestamp();

do $$ begin
 if exists(select 1 from public.plan_b_signals where status='active')
 or exists(select 1 from public.plan_b_real_trades where status='open')
 or exists(select 1 from public.plan_b_execution_intents where status in ('reserved','submitted','unknown','partial','open','closing'))
 then raise exception 'Stage45 transition requires no active B signals, trades, or intents'; end if;
end; $$;

alter table public.plan_b_signals drop constraint if exists plan_b_signals_symbol_check;
alter table public.plan_b_signals add constraint plan_b_signals_symbol_check
 check(symbol in ('AVAX','ICP','BCH','DOGE','UNI','ALGO','ETH','VET','LINK','DOT','LTC','BNB'));
alter table public.plan_b_execution_intents drop constraint if exists plan_b_execution_intents_symbol_check;
alter table public.plan_b_execution_intents add constraint plan_b_execution_intents_symbol_check
 check(symbol in ('AVAX','ICP','BCH','DOGE','UNI','ALGO','ETH','VET','LINK','DOT','LTC','BNB'));
alter table public.plan_b_execution_intents drop constraint if exists plan_b_execution_intents_client_order_id_check;
alter table public.plan_b_execution_intents add constraint plan_b_execution_intents_client_order_id_check
 check(client_order_id ~ '^pb(16|26|35|45)-[0-9]+$');

update public.plan_b_rules set target_fraction=case symbol
 when 'DOT' then .075 when 'BNB' then .125 else 1.15 end
where trade_group='supplement';
insert into public.plan_b_rules(symbol,trade_group,leverage,hold_hours,cooldown_hours,target_fraction)
values('BNB','supplement',3,1,2,.125)
on conflict(symbol) do update set trade_group=excluded.trade_group,leverage=excluded.leverage,
 hold_hours=excluded.hold_hours,cooldown_hours=excluded.cooldown_hours,target_fraction=excluded.target_fraction;

update public.plan_b_opportunity_state set payload=jsonb_set(
 jsonb_set(payload,'{version}','"b_core_bnb_stage45_v1"'::jsonb),
 '{nextEligibleAt}',coalesce(payload->'nextEligibleAt','{}'::jsonb)||jsonb_build_object(
 'BNB',(payload->>'lastConfirmedAt')::bigint)),updated_at=clock_timestamp()
where id='singleton' and payload->>'version'='b_core_idle_stage35_v1';

update public.plan_b_trading_state set strategy_id='b_core_bnb_stage45',
 validation_status='stage45_minute_verified_bnb_contract_configuration_ok',updated_at=clock_timestamp()
where id='singleton' and strategy_id='b_core_idle_stage35';

-- Preserve the already-reviewed atomic functions while moving their exact current
-- strategy/version/prefix constants to Stage45 and requiring all twelve decisions.
do $$ declare d text; begin
 select pg_get_functiondef('public.plan_b_claim_intent(text)'::regprocedure) into d;
 execute replace(replace(replace(d,'b_core_idle_stage35','b_core_bnb_stage45'),'pb35-','pb45-'),'pb35:','pb45:');
 select pg_get_functiondef('public.plan_b_publish_opportunities(bigint,jsonb)'::regprocedure) into d;
 d:=replace(replace(replace(replace(replace(d,'b_core_idle_stage35_v1','b_core_bnb_stage45_v1'),'b_core_idle_stage35','b_core_bnb_stage45'),'pb35:','pb45:'),'<> 11','<> 12'),'all eleven decisions required','all twelve decisions required');
 execute d;
 select pg_get_functiondef('public.plan_b_reserve_intents(jsonb,numeric,numeric,numeric,timestamp with time zone)'::regprocedure) into d;
 execute replace(replace(replace(d,'b_core_idle_stage35_v1','b_core_bnb_stage45_v1'),'b_core_idle_stage35','b_core_bnb_stage45'),'pb35-','pb45-');
end; $$;

commit;

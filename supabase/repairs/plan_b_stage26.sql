-- B-only additive upgrade. Does not alter enabled/test_mode, cron or A objects.
begin;
create table if not exists public.plan_b_opportunity_state(id text primary key check(id='singleton'),payload jsonb not null,updated_at timestamptz not null default now());
create table if not exists public.plan_b_opportunity_hours(confirmed_ms bigint primary key,decisions jsonb not null,state_after jsonb not null,created_at timestamptz not null default now());
create table if not exists public.plan_b_rules(symbol text primary key,trade_group text not null check(trade_group in ('core','supplement')),leverage numeric not null,hold_hours integer not null,cooldown_hours integer not null,target_fraction numeric not null);
insert into public.plan_b_rules values ('AVAX','core',3,13,13,1.15),('ICP','core',5,2,2,1.15),('BCH','core',3,4,4,1.15),('DOGE','core',5,13,13,1.15),('UNI','core',2,7,7,1.15),('ALGO','supplement',3,1,2,.9),('ETH','supplement',3,1,2,.9),('VET','supplement',3,1,2,.9)
on conflict(symbol) do update set trade_group=excluded.trade_group,leverage=excluded.leverage,hold_hours=excluded.hold_hours,cooldown_hours=excluded.cooldown_hours,target_fraction=excluded.target_fraction;
alter table public.plan_b_opportunity_state enable row level security;
alter table public.plan_b_opportunity_hours enable row level security;
alter table public.plan_b_rules enable row level security;
revoke all on public.plan_b_opportunity_state,public.plan_b_opportunity_hours,public.plan_b_rules from public,anon,authenticated;
grant all on public.plan_b_opportunity_state,public.plan_b_opportunity_hours to service_role;
grant select on public.plan_b_rules to service_role;
alter table public.plan_b_signals drop constraint if exists plan_b_signals_symbol_check;
alter table public.plan_b_signals add constraint plan_b_signals_symbol_check check(symbol in ('AVAX','ICP','BCH','DOGE','UNI','ALGO','ETH','VET'));
alter table public.plan_b_execution_intents drop constraint if exists plan_b_execution_intents_symbol_check;
alter table public.plan_b_execution_intents add constraint plan_b_execution_intents_symbol_check check(symbol in ('AVAX','ICP','BCH','DOGE','UNI','ALGO','ETH','VET'));
alter table public.plan_b_execution_intents drop constraint if exists plan_b_execution_intents_client_order_id_check;
alter table public.plan_b_execution_intents add constraint plan_b_execution_intents_client_order_id_check check(client_order_id ~ '^pb(16|26)-[0-9]+$');

create or replace function public.plan_b_publish_opportunities(p_expected bigint,p_steps jsonb) returns boolean
language plpgsql security invoker set search_path='' as $$
declare prev jsonb; step jsonb; expected jsonb; rule record; t bigint; busy bigint; nxt jsonb; selected text[]; side_value text; s jsonb; seen text[]; stamp timestamptz;
begin
 perform 1 from public.plan_b_trading_state where id='singleton' for update;
 select payload into prev from public.plan_b_opportunity_state where id='singleton' for update;
 if prev is null or prev->>'version'<>'b_core_sparse_stage26_v1' then raise exception 'opportunity bootstrap required'; end if;
 if (prev->>'lastConfirmedAt')::bigint is distinct from p_expected then return false; end if;
 if jsonb_typeof(p_steps) is distinct from 'array' or jsonb_array_length(p_steps) not between 1 and 800 then raise exception 'invalid recovery batch'; end if;
 for step in select value from jsonb_array_elements(p_steps) loop
  t:=(prev->>'lastConfirmedAt')::bigint+3600000;
  if (step->'state'->>'lastConfirmedAt')::bigint is distinct from t or t%3600000<>0 or to_timestamp(t/1000.0)>clock_timestamp() then raise exception 'nonchronological or future batch'; end if;
  if jsonb_typeof(step->'decisions') is distinct from 'object' or (select count(*) from jsonb_object_keys(step->'decisions'))<>8 then raise exception 'all eight decisions required'; end if;
  nxt:=prev->'nextEligibleAt';busy:=(prev->>'coreBusyUntil')::bigint;selected:='{}';seen:='{}';
  for rule in select * from public.plan_b_rules order by case when trade_group='core' then 0 else 1 end,symbol loop
   if not (step->'decisions' ? rule.symbol) or (step->'decisions'->rule.symbol->>'confirmedAt')::bigint is distinct from t then raise exception 'incomplete candle assessment'; end if;
   side_value:=step->'decisions'->rule.symbol->>'side';
   if side_value is not null and side_value not in ('long','short') then raise exception 'invalid side'; end if;
   if not(nxt ? rule.symbol) then raise exception 'incomplete cooldown state'; end if;
   if side_value is null or t<(nxt->>rule.symbol)::bigint or (rule.trade_group='supplement' and t<busy) then continue; end if;
   selected:=array_append(selected,rule.symbol);
   nxt:=jsonb_set(nxt,array[rule.symbol],to_jsonb(t+rule.cooldown_hours::bigint*3600000));
   if rule.trade_group='core' then busy:=greatest(busy,t+rule.hold_hours::bigint*3600000); end if;
  end loop;
  expected:=jsonb_build_object('version','b_core_sparse_stage26_v1','lastConfirmedAt',t,'coreBusyUntil',busy,'nextEligibleAt',nxt);
  if step->'state' is distinct from expected then raise exception 'opportunity rules/state mismatch'; end if;
  if jsonb_typeof(step->'signals') is distinct from 'array' or jsonb_array_length(step->'signals')<>cardinality(selected) then raise exception 'selected signals mismatch'; end if;
  stamp:=to_timestamp(t/1000.0);
  for s in select value from jsonb_array_elements(step->'signals') loop
   if not(s->>'symbol'=any(selected)) or s->>'symbol'=any(seen) then raise exception 'unexpected/duplicate symbol'; end if;
   seen:=array_append(seen,s->>'symbol');select * into rule from public.plan_b_rules where symbol=s->>'symbol';
   if s->>'strategy_id' is distinct from 'b_core_sparse_stage26' or s->>'side' is distinct from step->'decisions'->rule.symbol->>'side' or
    (s->>'confirmed_at')::timestamptz is distinct from stamp or (s->>'entry_deadline')::timestamptz is distinct from stamp+interval '5 minutes' or
    (s->>'expires_at')::timestamptz is distinct from stamp+make_interval(hours=>rule.hold_hours) or
    (s->>'leverage')::numeric is distinct from rule.leverage or (s->>'hold_hours')::integer is distinct from rule.hold_hours or
    (s->>'signal_price')::numeric<=0 or (s->>'signal_price') is null or (s->>'signal_price') in ('NaN','Infinity','-Infinity') then raise exception 'signal metadata mismatch'; end if;
   insert into public.plan_b_signals(signal_key,symbol,side,status,signal_price,volume_ratio,return_1h,realized_vol_24h,hold_hours,leverage,portfolio_weight,portfolio_scale,confirmed_at,entry_deadline,expires_at,strategy_id,strategy_params)
   values('pb26:'||rule.symbol||':'||t||':'||(s->>'side'),rule.symbol,s->>'side',case when clock_timestamp()<stamp+interval '5 minutes' then 'active' else 'expired' end,(s->>'signal_price')::numeric,coalesce((s->>'volume_ratio')::numeric,0),coalesce((s->>'return_1h')::numeric,0),0,rule.hold_hours,rule.leverage,1,1,stamp,stamp+interval '5 minutes',stamp+make_interval(hours=>rule.hold_hours),'b_core_sparse_stage26',s->'strategy_params');
  end loop;
  insert into public.plan_b_opportunity_hours(confirmed_ms,decisions,state_after) values(t,step->'decisions',expected);
  prev:=expected;
 end loop;
 update public.plan_b_opportunity_state set payload=prev,updated_at=clock_timestamp() where id='singleton';
 return true;
end $$;
revoke all on function public.plan_b_publish_opportunities(bigint,jsonb) from public,anon,authenticated;
grant execute on function public.plan_b_publish_opportunities(bigint,jsonb) to service_role;
commit;

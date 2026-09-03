begin;

do $$ begin
 if exists(select 1 from public.plan_b_signals where status='active')
 or exists(select 1 from public.plan_b_real_trades where status='open')
 or exists(select 1 from public.plan_b_execution_intents where status in ('reserved','submitted','unknown','partial','open','closing'))
 then raise exception 'Stage35 transition requires no active B signals, trades, or intents'; end if;
end; $$;

alter table public.plan_b_signals drop constraint if exists plan_b_signals_symbol_check;
alter table public.plan_b_signals add constraint plan_b_signals_symbol_check
 check(symbol in ('AVAX','ICP','BCH','DOGE','UNI','ALGO','ETH','VET','LINK','DOT','LTC'));

insert into public.plan_b_rules(symbol,trade_group,leverage,hold_hours,cooldown_hours,target_fraction) values
 ('LINK','supplement',3,1,2,.30),('DOT','supplement',3,1,2,.15),('LTC','supplement',3,1,2,.15)
on conflict(symbol) do update set trade_group=excluded.trade_group,leverage=excluded.leverage,hold_hours=excluded.hold_hours,cooldown_hours=excluded.cooldown_hours,target_fraction=excluded.target_fraction;

update public.plan_b_opportunity_state set payload=jsonb_set(
 jsonb_set(payload,'{version}','"b_core_idle_stage35_v1"'::jsonb),
 '{nextEligibleAt}',coalesce(payload->'nextEligibleAt','{}'::jsonb)||jsonb_build_object(
  'LINK',(payload->>'lastConfirmedAt')::bigint,'DOT',(payload->>'lastConfirmedAt')::bigint,'LTC',(payload->>'lastConfirmedAt')::bigint)),updated_at=clock_timestamp()
where id='singleton' and payload->>'version'='b_core_sparse_stage26_v1';

update public.plan_b_trading_state set strategy_id='b_core_idle_stage35',validation_status='stage35_delay_verified_contract_configuration_pending',updated_at=clock_timestamp() where id='singleton';

create or replace function public.plan_b_claim_intent(p_id text) returns boolean language plpgsql set search_path='' as $$
declare n integer;
begin
 perform 1 from public.plan_b_trading_state where id='singleton' and enabled and not test_mode and strategy_id in ('b_reserved_margin_stage16','b_core_sparse_stage26','b_core_idle_stage35') for update;
 if not found then return false; end if;
 update public.plan_b_execution_intents i set status='submitted',updated_at=now()
 from public.plan_b_signals s where i.signal_id=s.id and i.client_order_id=p_id and i.status='reserved' and s.entry_deadline>clock_timestamp() and s.strategy_id=(select strategy_id from public.plan_b_trading_state where id='singleton') and s.confirmed_at<=clock_timestamp() and clock_timestamp()-s.confirmed_at<interval '5 minutes';
 get diagnostics n=row_count;return n=1;
end; $$;

create or replace function public.plan_b_publish_opportunities(p_expected bigint,p_steps jsonb) returns boolean language plpgsql set search_path='' as $$
declare prev jsonb;step jsonb;expected jsonb;rule record;t bigint;busy bigint;nxt jsonb;selected text[];side_value text;s jsonb;seen text[];stamp timestamptz;
begin
 perform 1 from public.plan_b_trading_state where id='singleton' for update;
 select payload into prev from public.plan_b_opportunity_state where id='singleton' for update;
 if prev is null or prev->>'version'<>'b_core_idle_stage35_v1' then raise exception 'opportunity bootstrap required'; end if;
 if (prev->>'lastConfirmedAt')::bigint is distinct from p_expected then return false; end if;
 if jsonb_typeof(p_steps) is distinct from 'array' or jsonb_array_length(p_steps) not between 1 and 800 then raise exception 'invalid recovery batch'; end if;
 for step in select value from jsonb_array_elements(p_steps) loop
  t:=(prev->>'lastConfirmedAt')::bigint+3600000;
  if (step->'state'->>'lastConfirmedAt')::bigint is distinct from t or t%3600000<>0 or to_timestamp(t/1000.0)>clock_timestamp() then raise exception 'nonchronological or future batch'; end if;
  if jsonb_typeof(step->'decisions') is distinct from 'object' or (select count(*) from jsonb_object_keys(step->'decisions'))<>11 then raise exception 'all eleven decisions required'; end if;
  nxt:=prev->'nextEligibleAt';busy:=(prev->>'coreBusyUntil')::bigint;selected:='{}';seen:='{}';
  for rule in select * from public.plan_b_rules order by case when trade_group='core' then 0 else 1 end,symbol loop
   if not(step->'decisions'?rule.symbol) or (step->'decisions'->rule.symbol->>'confirmedAt')::bigint is distinct from t then raise exception 'incomplete candle assessment'; end if;
   side_value:=step->'decisions'->rule.symbol->>'side';
   if side_value is not null and side_value not in ('long','short') then raise exception 'invalid side'; end if;
   if not(nxt?rule.symbol) then raise exception 'incomplete cooldown state'; end if;
   if side_value is null or t<(nxt->>rule.symbol)::bigint or (rule.trade_group='supplement' and t<busy) then continue; end if;
   selected:=array_append(selected,rule.symbol);nxt:=jsonb_set(nxt,array[rule.symbol],to_jsonb(t+rule.cooldown_hours::bigint*3600000));
   if rule.trade_group='core' then busy:=greatest(busy,t+rule.hold_hours::bigint*3600000);end if;
  end loop;
  expected:=jsonb_build_object('version','b_core_idle_stage35_v1','lastConfirmedAt',t,'coreBusyUntil',busy,'nextEligibleAt',nxt);
  if step->'state' is distinct from expected then raise exception 'opportunity rules/state mismatch';end if;
  if jsonb_typeof(step->'signals') is distinct from 'array' or jsonb_array_length(step->'signals')<>cardinality(selected) then raise exception 'selected signals mismatch';end if;
  stamp:=to_timestamp(t/1000.0);
  for s in select value from jsonb_array_elements(step->'signals') loop
   if not(s->>'symbol'=any(selected)) or s->>'symbol'=any(seen) then raise exception 'unexpected/duplicate symbol';end if;
   seen:=array_append(seen,s->>'symbol');select * into rule from public.plan_b_rules where symbol=s->>'symbol';
   if s->>'strategy_id' is distinct from 'b_core_idle_stage35' or s->>'side' is distinct from step->'decisions'->rule.symbol->>'side' or (s->>'confirmed_at')::timestamptz is distinct from stamp or (s->>'entry_deadline')::timestamptz is distinct from stamp+interval '5 minutes' or (s->>'expires_at')::timestamptz is distinct from stamp+make_interval(hours=>rule.hold_hours) or (s->>'leverage')::numeric is distinct from rule.leverage or (s->>'hold_hours')::integer is distinct from rule.hold_hours or (s->>'signal_price')::numeric<=0 or (s->>'signal_price') is null or (s->>'signal_price') in ('NaN','Infinity','-Infinity') then raise exception 'signal metadata mismatch';end if;
   insert into public.plan_b_signals(signal_key,symbol,side,status,signal_price,volume_ratio,return_1h,realized_vol_24h,hold_hours,leverage,portfolio_weight,portfolio_scale,confirmed_at,entry_deadline,expires_at,strategy_id,strategy_params)
   values('pb35:'||rule.symbol||':'||t||':'||(s->>'side'),rule.symbol,s->>'side',case when clock_timestamp()<stamp+interval '5 minutes' then 'active' else 'expired' end,(s->>'signal_price')::numeric,coalesce((s->>'volume_ratio')::numeric,0),coalesce((s->>'return_1h')::numeric,0),0,rule.hold_hours,rule.leverage,1,1,stamp,stamp+interval '5 minutes',stamp+make_interval(hours=>rule.hold_hours),'b_core_idle_stage35',s->'strategy_params');
  end loop;
  insert into public.plan_b_opportunity_hours(confirmed_ms,decisions,state_after) values(t,step->'decisions',expected);prev:=expected;
 end loop;
 update public.plan_b_opportunity_state set payload=prev,updated_at=clock_timestamp() where id='singleton';return true;
end; $$;

create or replace function public.plan_b_reserve_intents(p_items jsonb,p_balance numeric,p_equity numeric,p_available numeric,p_snapshot timestamptz) returns jsonb language plpgsql set search_path='' as $$
declare st public.plan_b_trading_state;item jsonb;sig public.plan_b_signals;held numeric;demand numeric;available numeric;qty numeric;cost numeric;lev numeric;grp text;batch_group text;op jsonb;
begin
 select * into st from public.plan_b_trading_state where id='singleton' for update;
 if st.strategy_id not in ('b_reserved_margin_stage16','b_core_sparse_stage26','b_core_idle_stage35') or not st.enabled or st.test_mode then raise exception 'B live execution disabled';end if;
 if p_snapshot is null or p_snapshot>clock_timestamp() or clock_timestamp()-p_snapshot>interval '3 seconds' then raise exception 'stale account snapshot';end if;
 if exists(select 1 from public.plan_b_execution_intents where created_at>p_snapshot) then raise exception 'account snapshot predates reservation';end if;
 if p_balance is null or p_equity is null or p_available is null or least(p_balance,p_equity,p_available)<=0 or p_balance::text in ('NaN','Infinity','-Infinity') or p_equity::text in ('NaN','Infinity','-Infinity') or p_available::text in ('NaN','Infinity','-Infinity') then raise exception 'invalid account';end if;
 if jsonb_typeof(p_items) is distinct from 'array' or jsonb_array_length(p_items)=0 then raise exception 'empty batch';end if;
 if exists(select 1 from public.plan_b_execution_intents where status in ('submitted','unknown','partial','closing')) then raise exception 'B reconciliation required';end if;
 select payload into op from public.plan_b_opportunity_state where id='singleton';select coalesce(sum(reserved_usd),0) into held from public.plan_b_execution_intents where status not in ('closed','rejected','expired');
 available:=greatest(0,least(p_balance-held,p_equity-held,p_available)-p_equity*.05);select sum((value->>'reserved_usd')::numeric) into demand from jsonb_array_elements(p_items);
 if demand is null or demand::text in ('NaN','Infinity','-Infinity') or demand>available then raise exception 'B margin exhausted';end if;
 for item in select value from jsonb_array_elements(p_items) loop
  select * into sig from public.plan_b_signals where id=(item->>'signal_id')::bigint for update;
  if not found or sig.strategy_id<>st.strategy_id or sig.status<>'active' or sig.confirmed_at>clock_timestamp() or sig.entry_deadline<=clock_timestamp() or clock_timestamp()-sig.confirmed_at>=interval '5 minutes' then raise exception 'invalid or expired B signal';end if;
  qty:=(item->>'quantity')::numeric;cost:=(item->>'reserved_usd')::numeric;select leverage,trade_group into lev,grp from public.plan_b_rules where symbol=sig.symbol;
  if st.strategy_id in ('b_core_sparse_stage26','b_core_idle_stage35') then
   if op is null or op->>'version'<>(case when st.strategy_id='b_core_idle_stage35' then 'b_core_idle_stage35_v1' else 'b_core_sparse_stage26_v1' end) or (op->>'lastConfirmedAt')::bigint<>floor(extract(epoch from sig.confirmed_at)*1000)::bigint then raise exception 'B incomplete signal hour';end if;
   if batch_group is not null and grp<>batch_group then raise exception 'B mixed strategy groups';end if;batch_group:=grp;
   if exists(select 1 from public.plan_b_execution_intents i join public.plan_b_rules r on r.symbol=i.symbol where i.status not in ('closed','rejected','expired') and r.trade_group<>grp) then raise exception 'B opposite group reservation';end if;
   if grp='supplement' and (op->>'coreBusyUntil')::bigint>extract(epoch from clock_timestamp())*1000 then raise exception 'B core opportunity interval';end if;
  elsif grp<>'core' then raise exception 'Stage16 symbol rejected';end if;
  if lev is null or sig.leverage<>lev or qty is null or cost is null or qty<=0 or cost<=0 or qty::text in ('NaN','Infinity','-Infinity') or cost::text in ('NaN','Infinity','-Infinity') then raise exception 'invalid B reservation';end if;
  insert into public.plan_b_execution_intents(signal_id,client_order_id,symbol,side,quantity,reserved_usd,snapshot_at) values(sig.id,case when st.strategy_id='b_core_idle_stage35' then 'pb35-' when st.strategy_id='b_core_sparse_stage26' then 'pb26-' else 'pb16-' end||sig.id,sig.symbol,sig.side,qty,cost,p_snapshot);
 end loop;return jsonb_build_object('reserved_usd',demand,'available_before',available);
end; $$;

commit;

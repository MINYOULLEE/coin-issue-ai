begin;
create or replace function public.plan_b_reserve_intents(p_items jsonb,p_balance numeric,p_equity numeric,p_available numeric,p_snapshot timestamptz)
returns jsonb language plpgsql security invoker set search_path='' as $$
declare st public.plan_b_trading_state; item jsonb; sig public.plan_b_signals; held numeric; demand numeric; available numeric; qty numeric; cost numeric; lev numeric; grp text; batch_group text; op jsonb;
begin
 select * into st from public.plan_b_trading_state where id='singleton' for update;
 if st.strategy_id not in ('b_reserved_margin_stage16','b_core_sparse_stage26') or not st.enabled or st.test_mode then raise exception 'B live execution disabled'; end if;
 if p_snapshot is null or p_snapshot>clock_timestamp() or clock_timestamp()-p_snapshot>interval '3 seconds' then raise exception 'stale account snapshot'; end if;
 if exists(select 1 from public.plan_b_execution_intents where created_at>p_snapshot) then raise exception 'account snapshot predates reservation'; end if;
 if p_balance is null or p_equity is null or p_available is null or least(p_balance,p_equity,p_available)<=0 or
 p_balance::text in ('NaN','Infinity','-Infinity') or p_equity::text in ('NaN','Infinity','-Infinity') or p_available::text in ('NaN','Infinity','-Infinity') then raise exception 'invalid account'; end if;
 if jsonb_typeof(p_items) is distinct from 'array' or jsonb_array_length(p_items)=0 then raise exception 'empty batch'; end if;
 if exists(select 1 from public.plan_b_execution_intents where status in ('submitted','unknown','partial','closing')) then raise exception 'B reconciliation required'; end if;
 select payload into op from public.plan_b_opportunity_state where id='singleton';
 select coalesce(sum(reserved_usd),0) into held from public.plan_b_execution_intents where status not in ('closed','rejected','expired');
 available:=greatest(0,least(p_balance-held,p_equity-held,p_available)-p_equity*.05);
 select sum((value->>'reserved_usd')::numeric) into demand from jsonb_array_elements(p_items);
 if demand is null or demand::text in ('NaN','Infinity','-Infinity') or demand>available then raise exception 'B margin exhausted'; end if;
 for item in select value from jsonb_array_elements(p_items) loop
  select * into sig from public.plan_b_signals where id=(item->>'signal_id')::bigint for update;
  if not found or sig.strategy_id<>st.strategy_id or sig.status<>'active' or sig.confirmed_at>clock_timestamp() or sig.entry_deadline<=clock_timestamp() or clock_timestamp()-sig.confirmed_at>=interval '5 minutes' then raise exception 'invalid or expired B signal'; end if;
  qty:=(item->>'quantity')::numeric;cost:=(item->>'reserved_usd')::numeric;
  select leverage,trade_group into lev,grp from public.plan_b_rules where symbol=sig.symbol;
  if st.strategy_id='b_core_sparse_stage26' then
   if op is null or op->>'version'<>'b_core_sparse_stage26_v1' or (op->>'lastConfirmedAt')::bigint <> floor(extract(epoch from sig.confirmed_at)*1000)::bigint then raise exception 'B incomplete signal hour'; end if;
   if batch_group is not null and grp<>batch_group then raise exception 'B mixed strategy groups'; end if;
   batch_group:=grp;
   if exists(select 1 from public.plan_b_execution_intents i join public.plan_b_rules r on r.symbol=i.symbol where i.status not in ('closed','rejected','expired') and r.trade_group<>grp) then raise exception 'B opposite group reservation'; end if;
   if grp='supplement' and (op->>'coreBusyUntil')::bigint>extract(epoch from clock_timestamp())*1000 then raise exception 'B core opportunity interval'; end if;
  elsif grp<>'core' then raise exception 'Stage16 symbol rejected'; end if;
  if lev is null or sig.leverage<>lev or qty is null or cost is null or qty<=0 or cost<=0 or qty::text in ('NaN','Infinity','-Infinity') or cost::text in ('NaN','Infinity','-Infinity') then raise exception 'invalid B reservation'; end if;
  insert into public.plan_b_execution_intents(signal_id,client_order_id,symbol,side,quantity,reserved_usd,snapshot_at)
   values(sig.id,case when st.strategy_id='b_core_sparse_stage26' then 'pb26-' else 'pb16-' end||sig.id,sig.symbol,sig.side,qty,cost,p_snapshot);
 end loop;
 return jsonb_build_object('reserved_usd',demand,'available_before',available);
end $$;
revoke all on function public.plan_b_reserve_intents(jsonb,numeric,numeric,numeric,timestamptz) from public,anon,authenticated;
grant execute on function public.plan_b_reserve_intents(jsonb,numeric,numeric,numeric,timestamptz) to service_role;
create or replace function public.plan_b_claim_intent(p_id text)
returns boolean language plpgsql security invoker set search_path='' as $$
declare n integer;
begin
 perform 1 from public.plan_b_trading_state where id='singleton' and enabled and not test_mode and strategy_id in ('b_reserved_margin_stage16','b_core_sparse_stage26') for update;
 if not found then return false; end if;
 update public.plan_b_execution_intents i set status='submitted',updated_at=now()
 from public.plan_b_signals s where i.signal_id=s.id and i.client_order_id=p_id and i.status='reserved' and s.entry_deadline>clock_timestamp() and s.strategy_id=(select strategy_id from public.plan_b_trading_state where id='singleton') and s.confirmed_at<=clock_timestamp() and clock_timestamp()-s.confirmed_at<interval '5 minutes';
 get diagnostics n=row_count;return n=1;
end $$;
revoke all on function public.plan_b_claim_intent(text) from public,anon,authenticated;
grant execute on function public.plan_b_claim_intent(text) to service_role;
commit;

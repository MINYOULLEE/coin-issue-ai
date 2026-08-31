-- Entire diagnostic transaction rolls back. No exchange requests, no durable test trades.
begin;
do $$
declare original_state jsonb; base jsonb; after_state jsonb; decisions jsonb; t bigint; s bigint; extra bigint; res jsonb; before_count bigint; rejected boolean;
begin
 select to_jsonb(x) into original_state from public.plan_b_trading_state x where id='singleton' for update;
 t:=floor(extract(epoch from date_trunc('hour',clock_timestamp()))*1000)::bigint;
 base:=jsonb_build_object('version','b_core_sparse_stage26_v1','lastConfirmedAt',t-3600000,'coreBusyUntil',0,'nextEligibleAt',(select jsonb_object_agg(symbol,0) from public.plan_b_rules));
 insert into public.plan_b_opportunity_state(id,payload) values('singleton',base) on conflict(id) do update set payload=excluded.payload;
 decisions:=(select jsonb_object_agg(symbol,jsonb_build_object('side',null,'confirmedAt',t)) from public.plan_b_rules);
 after_state:=jsonb_set(base,'{lastConfirmedAt}',to_jsonb(t));
 if not public.plan_b_publish_opportunities(t-3600000,jsonb_build_array(jsonb_build_object('state',after_state,'decisions',decisions,'signals','[]'::jsonb))) then raise exception 'publish failed'; end if;
 if public.plan_b_publish_opportunities(t-3600000,'[]'::jsonb) then raise exception 'duplicate advance'; end if;
 rejected:=false;
 begin perform public.plan_b_publish_opportunities(t,jsonb_build_array(jsonb_build_object('state',jsonb_set(after_state,'{lastConfirmedAt}',to_jsonb(t+3600000)),'decisions',decisions-'ICP','signals','[]'::jsonb)));exception when others then rejected:=true;end;
 if not rejected then raise exception 'missing assessment accepted';end if;
 -- New reservations are exercised inside this transaction only, using generated IDs.
 update public.plan_b_trading_state set strategy_id='b_core_sparse_stage26' where id='singleton';
 if not (original_state->>'enabled')::boolean or (original_state->>'test_mode')::boolean then raise exception 'owner state does not permit reservation test'; end if;
 t:=floor(extract(epoch from clock_timestamp())*1000)::bigint;
 update public.plan_b_opportunity_state set payload=jsonb_set(jsonb_set(after_state,'{lastConfirmedAt}',to_jsonb(t)),'{coreBusyUntil}','0');
 insert into public.plan_b_signals(signal_key,symbol,side,status,signal_price,volume_ratio,return_1h,realized_vol_24h,hold_hours,leverage,portfolio_weight,portfolio_scale,confirmed_at,entry_deadline,expires_at,strategy_id)
 values('stage26-rollback-core-'||txid_current(),'AVAX','long','active',10,0,0,0,13,3,1,1,to_timestamp(t/1000.0),to_timestamp(t/1000.0)+interval '5 minutes',to_timestamp(t/1000.0)+interval '13 hours','b_core_sparse_stage26') returning id into s;
 insert into public.plan_b_signals(signal_key,symbol,side,status,signal_price,volume_ratio,return_1h,realized_vol_24h,hold_hours,leverage,portfolio_weight,portfolio_scale,confirmed_at,entry_deadline,expires_at,strategy_id)
 values('stage26-rollback-extra-'||txid_current(),'ETH','long','active',100,0,0,0,1,3,1,1,to_timestamp(t/1000.0),to_timestamp(t/1000.0)+interval '5 minutes',to_timestamp(t/1000.0)+interval '1 hour','b_core_sparse_stage26') returning id into extra;
 res:=public.plan_b_reserve_intents(jsonb_build_array(jsonb_build_object('signal_id',extra,'quantity',1,'reserved_usd',50)),150,150,150,clock_timestamp());
 if (res->>'reserved_usd')::numeric<>50 then raise exception 'reservation failed';end if;
 rejected:=false;
 begin perform public.plan_b_reserve_intents(jsonb_build_array(jsonb_build_object('signal_id',s,'quantity',1,'reserved_usd',20)),150,150,100,clock_timestamp());exception when others then if sqlerrm not like '%opposite group%' then raise;end if;rejected:=true;end;
 if not rejected then raise exception 'group overlap accepted';end if;
 if not public.plan_b_claim_intent('pb26-'||extra) then raise exception 'claim failed';end if;
 if public.plan_b_claim_intent('pb26-'||extra) then raise exception 'duplicate claim';end if;
end $$;
rollback;
select 'PASS: atomic publish, duplicate CAS, missing assessment, margin reservation, opposite-group exclusion, single claim; all test writes rolled back' as result;

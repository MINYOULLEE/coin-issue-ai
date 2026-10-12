-- User-approved Stage170 exit-only upgrade. Signal grammar/IDs and switches stay unchanged.
alter table public.plan_b_real_trades add column if not exists continuation_until timestamptz;
alter table public.plan_b_real_trades add column if not exists continuation_count integer not null default 0;
alter table public.plan_b_real_trades add column if not exists continuation_history jsonb not null default '[]'::jsonb;

create or replace function public.plan_b_continue_icp(
 p_trade_id bigint,p_signal_id bigint,p_balance numeric,p_equity numeric,p_available numeric,
 p_gross numeric,p_mark numeric,p_owned_quantity numeric,p_snapshot timestamptz
) returns boolean language plpgsql security invoker set search_path='' as $$
declare st public.plan_b_trading_state;tr public.plan_b_real_trades;old public.plan_b_signals;
 next public.plan_b_signals;intent public.plan_b_execution_intents;held numeric;room numeric;due timestamptz;
begin
 -- Same singleton lock as reservation/publication; no credentials or order submission in SQL.
 select * into st from public.plan_b_trading_state where id='singleton' for update;
 if st.strategy_id<>'b_regime_guard_stage112' or not st.enabled or st.test_mode or st.validation_status not like 'stage170_%' then return false;end if;
 select * into intent from public.plan_b_execution_intents where signal_id=(select signal_id from public.plan_b_real_trades where id=p_trade_id) for update;
 if not found or intent.status<>'open' then return false;end if;
 select * into tr from public.plan_b_real_trades where id=p_trade_id for update;
 if tr.status<>'open' or tr.symbol<>'ICP' or tr.control_marker=2 or tr.bingx_order_id is null then return false;end if;
 select * into old from public.plan_b_signals where id=tr.signal_id;
 select * into next from public.plan_b_signals where id=p_signal_id for update;
 if not found then return false;end if;
 due:=coalesce(tr.continuation_until,old.expires_at);
 if next.strategy_id<>st.strategy_id or next.symbol<>'ICP' or next.side<>tr.side or next.status<>'active' or next.dispatched_at is not null or next.confirmed_at<>due or next.confirmed_at>clock_timestamp() or clock_timestamp()-next.confirmed_at>=interval '5 minutes' or next.entry_deadline<=clock_timestamp() or next.hold_hours<>2 or next.leverage<>5 or next.expires_at<>due+interval '2 hours' or next.expires_at>old.confirmed_at+interval '8 hours' then return false;end if;
 if p_snapshot is null or p_snapshot>clock_timestamp() or clock_timestamp()-p_snapshot>interval '3 seconds' then return false;end if;
 if p_balance is null or p_equity is null or p_available is null or p_gross is null or p_mark is null or p_owned_quantity is null or least(p_balance,p_equity,p_mark)<=0 or least(p_available,p_gross,p_owned_quantity)<0 or p_balance::text in ('NaN','Infinity','-Infinity') or p_equity::text in ('NaN','Infinity','-Infinity') or p_available::text in ('NaN','Infinity','-Infinity') or p_gross::text in ('NaN','Infinity','-Infinity') or p_mark::text in ('NaN','Infinity','-Infinity') or p_owned_quantity::text in ('NaN','Infinity','-Infinity') then return false;end if;
 if st.risk_pause_until is not null or st.risk_updated_at is null or clock_timestamp()-st.risk_updated_at>interval '10 seconds' or st.risk_last_equity_usdt/st.risk_equity_peak_usdt-1<=-.25 or p_gross>3.75*p_equity or p_owned_quantity<tr.quantity then return false;end if;
 if tr.profit_lock_armed_at is not null and ((tr.side='long' and p_mark<=tr.profit_lock_floor_price) or (tr.side='short' and p_mark>=tr.profit_lock_floor_price)) then return false;end if;
 if exists(select 1 from public.plan_b_execution_intents where status in ('submitted','unknown','partial','closing')) then return false;end if;
 select coalesce(sum(reserved_usd),0) into held from public.plan_b_execution_intents where status not in ('closed','rejected','expired');
 room:=greatest(0,least(p_balance-held,p_equity-held)-p_equity*.05);
 if least(room,p_available)<tr.quantity*p_mark*.0000125*2 then return false;end if;
 update public.plan_b_real_trades set continuation_until=next.expires_at,continuation_count=continuation_count+1,
  continuation_history=continuation_history||jsonb_build_array(jsonb_build_object('signal_id',next.id,'boundary',next.confirmed_at,'expires_at',next.expires_at,'committed_at',clock_timestamp())),updated_at=clock_timestamp() where id=tr.id;
 -- Makes stale concurrent scheduled-close claims fail their updated_at CAS.
 update public.plan_b_execution_intents set updated_at=clock_timestamp() where id=intent.id;
 update public.plan_b_signals set status='closed',dispatched_at=clock_timestamp(),dispatch_block_reason='continued_existing_position',dispatch_checked_at=clock_timestamp(),updated_at=clock_timestamp() where id=next.id;
 return true;
end;$$;
revoke all on function public.plan_b_continue_icp(bigint,bigint,numeric,numeric,numeric,numeric,numeric,numeric,timestamptz) from public,anon,authenticated;
grant execute on function public.plan_b_continue_icp(bigint,bigint,numeric,numeric,numeric,numeric,numeric,numeric,timestamptz) to service_role;
comment on function public.plan_b_continue_icp(bigint,bigint,numeric,numeric,numeric,numeric,numeric,numeric,timestamptz) is 'Stage170: atomically consume a selected same-side ICP signal without changing quantity, original signal expiry or profit floor.';

create or replace function public.plan_b_claim_stage170_close(p_trade_id bigint,p_intent_id bigint,p_updated_at timestamptz,p_reason text,p_quantity numeric,p_manual numeric,p_attempt integer,p_client_order_id text)
returns table(id bigint) language plpgsql security invoker set search_path='' as $$
declare tr public.plan_b_real_trades;i public.plan_b_execution_intents;due timestamptz;
begin
 perform 1 from public.plan_b_trading_state where plan_b_trading_state.id='singleton' for update;
 select * into i from public.plan_b_execution_intents where plan_b_execution_intents.id=p_intent_id for update;
 if not found then return;end if;
 select * into tr from public.plan_b_real_trades where plan_b_real_trades.id=p_trade_id for update;
 if not found then return;end if;
 if tr.symbol<>'ICP' or tr.status<>'open' or i.signal_id<>tr.signal_id or i.status not in ('open','closing') or i.updated_at is distinct from p_updated_at or i.close_attempt+1<>p_attempt or p_quantity is null or p_quantity<=0 or p_quantity>tr.quantity or p_manual is null or p_manual<0 or p_reason not in ('scheduled_time','profit_lock') or p_client_order_id is distinct from tr.client_order_id||'-c'||p_attempt then return;end if;
 select coalesce(tr.continuation_until,s.expires_at) into due from public.plan_b_signals s where s.id=tr.signal_id;
 if p_reason='scheduled_time' and due>clock_timestamp() then return;end if;
 return query update public.plan_b_execution_intents set status='closing',close_attempt=p_attempt,close_client_order_id=p_client_order_id,close_quantity=p_quantity,manual_remainder_qty=p_manual,updated_at=clock_timestamp() where plan_b_execution_intents.id=i.id returning plan_b_execution_intents.id;
end;$$;
revoke all on function public.plan_b_claim_stage170_close(bigint,bigint,timestamptz,text,numeric,numeric,integer,text) from public,anon,authenticated;
grant execute on function public.plan_b_claim_stage170_close(bigint,bigint,timestamptz,text,numeric,numeric,integer,text) to service_role;

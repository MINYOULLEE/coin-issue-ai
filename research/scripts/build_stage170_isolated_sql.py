"""Print isolated pg_temp tests. Never update public trading records."""
from pathlib import Path
import re
ROOT=Path(__file__).resolve().parents[2]
source=(ROOT/'supabase/migrations/20261012102923_plan_b_stage170_icp_continuation.sql').read_text(encoding='utf-8')
functions=re.findall(r'create or replace function public\.plan_b_(?:continue_icp|claim_stage170_close)\(.*?end;\$\$;',source,re.S)
assert len(functions)==2
print('begin;')
for table in ('plan_b_trading_state','plan_b_execution_intents','plan_b_real_trades','plan_b_signals'):
    print(f'create temporary table {table} (like public.{table} including defaults);')
for fn in functions:
    print(fn.replace('public.plan_b_', 'pg_temp.plan_b_'))
print("""
insert into pg_temp.plan_b_trading_state(id,strategy_id,enabled,test_mode,validation_status,risk_equity_peak_usdt,risk_last_equity_usdt,risk_updated_at)
values('singleton','b_regime_guard_stage112',true,false,'stage170_isolated_fixture',100,100,clock_timestamp());
insert into pg_temp.plan_b_signals(id,signal_key,symbol,side,status,signal_price,volume_ratio,return_1h,realized_vol_24h,portfolio_weight,hold_hours,leverage,confirmed_at,entry_deadline,expires_at,strategy_id)
values(-36,'isolated-root','ICP','short','active',3,1,0,0,1,2,5,date_trunc('minute',clock_timestamp())-interval '2 hours',clock_timestamp()-interval '1 hour',date_trunc('minute',clock_timestamp()),'b_regime_guard_stage112'),
(-37,'isolated-next','ICP','short','active',3,1,0,0,1,2,5,date_trunc('minute',clock_timestamp()),date_trunc('minute',clock_timestamp())+interval '5 minutes',date_trunc('minute',clock_timestamp())+interval '2 hours','b_regime_guard_stage112');
insert into pg_temp.plan_b_real_trades(id,signal_id,symbol,side,status,entry_price,quantity,leverage,margin_usd,bingx_order_id,client_order_id,control_marker)
values(-7,-36,'ICP','short','open',3,10,5,6,'isolated-order','pb112-isolated',1);
insert into pg_temp.plan_b_execution_intents(id,signal_id,client_order_id,symbol,side,status,quantity,reserved_usd,snapshot_at,updated_at)
values(-7,-36,'pb112-isolated','ICP','short','open',10,30,clock_timestamp(),clock_timestamp());
do $$ declare ok boolean;n integer;stamp timestamptz;begin
 ok:=pg_temp.plan_b_continue_icp(-7,-37,100,100,50,376,3,10,clock_timestamp());if ok then raise exception 'gross cap bypass';end if;
 ok:=pg_temp.plan_b_continue_icp(-7,-37,100,100,0,30,3,10,clock_timestamp());if ok then raise exception 'free margin bypass';end if;
 update pg_temp.plan_b_trading_state set risk_pause_until=clock_timestamp()+interval '1 hour';
 ok:=pg_temp.plan_b_continue_icp(-7,-37,100,100,50,30,3,10,clock_timestamp());if ok then raise exception 'risk pause bypass';end if;
 update pg_temp.plan_b_trading_state set risk_pause_until=null;
 select updated_at into stamp from pg_temp.plan_b_execution_intents where id=-7;
 ok:=pg_temp.plan_b_continue_icp(-7,-37,100,100,50,30,3,10,clock_timestamp());if not ok then raise exception 'valid continuation rejected';end if;
 if (select quantity from pg_temp.plan_b_real_trades where id=-7)<>10 or (select continuation_count from pg_temp.plan_b_real_trades where id=-7)<>1 then raise exception 'quantity/count mismatch';end if;
 if (select expires_at from pg_temp.plan_b_signals where id=-36)<>date_trunc('minute',clock_timestamp()) then raise exception 'original expiry changed';end if;
 ok:=pg_temp.plan_b_continue_icp(-7,-37,100,100,50,30,3,10,clock_timestamp());if ok then raise exception 'duplicate consumed';end if;
 select count(*) into n from pg_temp.plan_b_claim_stage170_close(-7,-7,stamp,'scheduled_time',10,0,1,'pb112-isolated-c1');if n<>0 then raise exception 'stale CAS allowed close';end if;
 select count(*) into n from pg_temp.plan_b_claim_stage170_close(-7,-7,(select updated_at from pg_temp.plan_b_execution_intents where id=-7),'scheduled_time',10,0,1,'pb112-isolated-c1');if n<>0 then raise exception 'extended deadline allowed close';end if;
 select count(*) into n from pg_temp.plan_b_claim_stage170_close(-7,-7,(select updated_at from pg_temp.plan_b_execution_intents where id=-7),'profit_lock',10,0,1,'pb112-isolated-c1');if n<>1 then raise exception 'profit lock unable to close';end if;
end $$;
rollback;
select 'PASS: isolated pg_temp fixtures only; no public trading state/record mutations; gross/free-margin/risk guards, fixed quantity, duplicate signal, stale close CAS, extended expiry and profit close' verification;
""")

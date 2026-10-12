import standard from './plan_b_standard.json' with {type:'json'};
const H=3600000;
// No orders or writes. The DB transaction is the sole commit authority.
export function continuationDecision({trade,signal,now,balance,equity,availableMargin,reservedMargin,gross,entryAllowed,intentStatus='open',ownedQuantity}){
 const fail=reason=>({ok:false,reason});
 if(!standard.icp_continuation?.enabled||trade.symbol!=='ICP'||trade.side!==signal?.side||Number(trade.control_marker??1)===2||intentStatus!=='open')return fail('not_eligible');
 const original=Date.parse(trade.signal_confirmed_at||trade.plan_b_signals?.confirmed_at),due=Date.parse(trade.continuation_until||trade.plan_b_signals?.expires_at);
 const confirmed=Date.parse(signal.confirmed_at),deadline=Date.parse(signal.expires_at),ttl=Date.parse(signal.entry_deadline);
 if(![original,due,confirmed,deadline,ttl,now].every(Number.isFinite)||confirmed!==due||now<due||now-confirmed>=300000||ttl<=now)return fail('boundary_or_ttl');
 if(signal.strategy_id!==standard.strategy_id||signal.status!=='active'||signal.dispatched_at||Number(signal.leverage)!==5||Number(signal.hold_hours)!==2||deadline!==confirmed+2*H||deadline>original+8*H)return fail('signal_or_max_hold');
 if(![balance,equity,availableMargin,reservedMargin,gross,ownedQuantity,Number(trade.quantity)].every(Number.isFinite)||equity<=0||reservedMargin<0||gross<0||ownedQuantity<Number(trade.quantity)-1e-10)return fail('invalid_snapshot_or_quantity');
 if(!entryAllowed)return fail('risk_pause');
 if(gross>equity*3.75)return fail('gross_cap');
 const quantity=Number(trade.quantity),mark=Number(trade.continuation_mark);
 if(!(mark>0)||!Number.isFinite(mark))return fail('invalid_mark');
 const fundingRoom=quantity*mark*standard.research_costs.funding_hourly*2;
 const room=Math.max(0,Math.min(balance-reservedMargin,equity-reservedMargin)-equity*.05);
 if(Math.min(room,availableMargin)<fundingRoom)return fail('funding_room');
 return {ok:true,expiresAt:new Date(deadline).toISOString(),signalId:signal.id,fundingRoom};
}

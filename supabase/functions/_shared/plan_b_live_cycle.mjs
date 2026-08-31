import {allocatePlanB,PLAN_B_STANDARD as STANDARD} from './plan_b_sizing.mjs';
import {constrainBQuantity} from './plan_b_exchange.mjs';

export async function checked(query) { const {data,error}=await query;if(error)throw error;return data; }
export function selectExecutionGroup(signals,intents){
 const group=signals.some(s=>STANDARD.symbols[s.symbol]?.group==='core')?'core':'supplement';
 if(intents.some(i=>!STANDARD.symbols[i.symbol]||STANDARD.symbols[i.symbol].group!==group))return [];
 return signals.filter(s=>STANDARD.symbols[s.symbol]?.group===group);
}
export function eligible(signal,now=Date.now()) {
 const rule=STANDARD.symbols[signal.symbol];
 return !!rule && signal.strategy_id===STANDARD.strategy_id && ['long','short'].includes(signal.side) &&
  Number(signal.leverage)===rule.leverage && Number(signal.hold_hours)===rule.actual_hold_hours &&
  Date.parse(signal.confirmed_at)<=now && now-Date.parse(signal.confirmed_at)<300000 && Date.parse(signal.entry_deadline)>now;
}
export function fillValid(fill,quantity) {return ['filled','partially_filled'].includes(fill.status)&&!!fill.orderId&&Number.isFinite(fill.price)&&fill.price>0&&Number.isFinite(fill.quantity)&&fill.quantity>0&&fill.quantity<=quantity;}
export function positionQuantity(raw,symbol,side) {
 const rows=Array.isArray(raw)?raw:raw?.positions;if(!Array.isArray(rows))throw Error('invalid position response');
 return rows.filter(p=>p.symbol===symbol+'-USDT'&&p.positionSide===side.toUpperCase()).reduce((sum,p)=>{const q=Number(p.positionAmt??p.positionAmount);if(!Number.isFinite(q))throw Error('invalid position quantity');return sum+Math.abs(q);},0);
}
export function historySettlement(raw,trade) {
 const rows=Array.isArray(raw)?raw:raw?.positionHistory||raw?.positions||raw?.list;
 if(!Array.isArray(rows))return null;
 const opened=Date.parse(trade.filled_at||trade.created_at);
 const matches=rows.filter(p=>String(p.symbol)===trade.symbol+'-USDT'&&String(p.positionSide).toLowerCase()===trade.side&&
  Math.abs(Number(p.openTime??p.positionTime??p.createTime)-opened)<=120000&&Number(p.closeTime)>opened);
 if(matches.length!==1)return null;
 const p=matches[0],net=Number(p.netProfit),price=Number(p.avgClosePrice??p.closeAvgPrice??p.closePrice);
 // Missing netProfit is not zero: do not guess whether a gross field includes funding.
 if(p.netProfit==null||!Number.isFinite(net)||!Number.isFinite(price)||price<=0)return null;
 return {net_pnl_usd:net,close_price:price,fee_usd:p.commission==null?null:Math.abs(Number(p.commission)),closed_at:new Date(Number(p.closeTime)).toISOString()};
}
export async function executeBatch({sb,bx,now=Date.now}) {
 const state=await checked(sb.from('plan_b_trading_state').select('*').eq('id','singleton').single());
 if(state.strategy_id!==STANDARD.strategy_id)throw Error('B strategy mismatch');
 if(!state.enabled||state.test_mode)return {mode:'paused',processed:0}; // never create paper real-trades
 const intents=await checked(sb.from('plan_b_execution_intents').select('*').not('status','in','(closed,rejected,expired)'))||[];
 // All uncertain submissions must be reconciled before allocating additional funds.
 if(intents.some(i=>['submitted','unknown','partial','closing'].includes(i.status)))return {mode:'reconciliation_required',processed:0};
 const pending=await checked(sb.from('plan_b_signals').select('*').eq('status','active').is('dispatched_at',null).gt('entry_deadline',new Date(now()).toISOString()).order('id'))||[];
 const occupied=new Set(intents.map(i=>i.symbol)),seen=new Set();
 const signals=selectExecutionGroup(pending.filter(s=>{if(!eligible(s,now())||occupied.has(s.symbol)||seen.has(s.symbol))return false;seen.add(s.symbol);return true;}),intents);
 if(!signals.length)return {mode:'live',processed:0};
 const livePositions=await bx.read('/openApi/swap/v2/user/positions',{});
 const liveRows=Array.isArray(livePositions)?livePositions:livePositions?.positions;
 if(!Array.isArray(liveRows))throw Error('invalid position response');
 for(const p of liveRows){const q=Number(p.positionAmt??p.positionAmount);if(!Number.isFinite(q))throw Error('invalid position quantity');if(Math.abs(q)>0&&!occupied.has(String(p.symbol).replace('-USDT','')))throw Error('untracked B account position');}
 const contracts=await bx.read('/openApi/swap/v2/quote/contracts',{});
 const proposals=[];
 for(const signal of signals){
  // Configuration failure aborts the batch. No order may use an unverified leverage.
  const capabilities=await bx.verifyConfiguration(signal.symbol,Number(signal.leverage));
  const marks=await bx.read('/openApi/swap/v2/quote/premiumIndex',{symbol:signal.symbol+'-USDT'}),price=Number((Array.isArray(marks)?marks[0]:marks)?.markPrice);
  const adverse=(price/Number(signal.signal_price)-1)*100*(signal.side==='long'?1:-1);
  if(!Number.isFinite(adverse)||adverse>.35)continue;
  proposals.push({symbol:signal.symbol,entryPrice:price,signal,capabilities});
 }
 if(!proposals.length)return {mode:'live',processed:0};
 const snapshot=new Date(now()).toISOString();
 const balanceRaw=await bx.read('/openApi/swap/v3/user/balance',{}),balances=Array.isArray(balanceRaw)?balanceRaw:Array.isArray(balanceRaw?.balance)?balanceRaw.balance:[balanceRaw?.balance||balanceRaw];
 const account=balances.find(b=>b.asset==='USDT');if(!account)throw Error('USDT unavailable');
 const balance=Number(account.balance),equity=Number(account.equity),free=Number(account.availableMargin);
 if(![balance,equity,free].every(Number.isFinite))throw Error('invalid balance');
 const held=intents.reduce((s,i)=>s+Number(i.reserved_usd),0);
 const allocation=allocatePlanB({plan:'B',strategyId:STANDARD.strategy_id,balance,equity,reservedMargin:held,proposals});
 const required=allocation.orders.reduce((s,o)=>s+o.requiredReservation,0),ratio=required>0?Math.min(1,Math.max(0,free-equity*.05)/required):0;
 if(ratio<=0)return {mode:'insufficient_free_margin',processed:0};
 const orders=allocation.orders.map((order,i)=>{
  const proposal=proposals[i],contract={...contracts.find(c=>c.symbol===order.symbol+'-USDT'),...proposal.capabilities};
  const sized=constrainBQuantity({...order,side:proposal.signal.side,quantity:order.quantity*ratio},contract,proposal.entryPrice);
  return {...sized,signal:proposal.signal,reservation:order.requiredReservation*ratio,clientOrderId:STANDARD.isolation.client_order_prefix+'-'+proposal.signal.id};
 });
 // One database transaction reserves the complete batch and serializes competing invocations.
 await checked(sb.rpc('plan_b_reserve_intents',{p_items:orders.map(o=>({signal_id:o.signal.id,quantity:o.quantity,reserved_usd:o.reservation})),p_balance:balance,p_equity:equity,p_available:free,p_snapshot:snapshot}));
 const results=[];
 for(const order of orders){
  const claimed=await checked(sb.rpc('plan_b_claim_intent',{p_id:order.clientOrderId}));if(!claimed)continue;
  let submissionPossible=false;
  try{
   const stateNow=await checked(sb.from('plan_b_trading_state').select('*').eq('id','singleton').single());
   if(stateNow.strategy_id!==STANDARD.strategy_id||!stateNow.enabled||stateNow.test_mode||!eligible(order.signal,now()))throw Error('entry disabled or expired before submit');
   const observed=await bx.lookup(order);
   let fill=observed;submissionPossible=observed.status!=='not_found';
   if(observed.status==='not_found'){
    const marks=await bx.read('/openApi/swap/v2/quote/premiumIndex',{symbol:order.symbol+'-USDT'}),price=Number((Array.isArray(marks)?marks[0]:marks)?.markPrice);
    if((price/Number(order.signal.signal_price)-1)*100*(order.side==='long'?1:-1)>.35||!Number.isFinite(price))throw Error('price moved before submit');
    if(!eligible(order.signal,now()))throw Error('entry expired');
    submissionPossible=true;fill=await bx.submit(order);
   }
   await recordEntry({sb,order,fill,now});results.push({symbol:order.symbol,status:fill.status});
  }catch(error){const status=submissionPossible?'unknown':'expired';await checked(sb.from('plan_b_execution_intents').update({status,updated_at:new Date(now()).toISOString()}).eq('client_order_id',order.clientOrderId));results.push({symbol:order.symbol,status,error:String(error.message)});}
 }
 return {ok:results.every(r=>!r.error),mode:'live',processed:results.length,results};
}
export async function recordEntry({sb,order,fill,now=Date.now}) {
 if(!fillValid(fill,Number(order.quantity))){
  const status=fill.status==='rejected'&&fill.quantity===0?'rejected':'unknown';
  await checked(sb.from('plan_b_execution_intents').update({status,updated_at:new Date(now()).toISOString()}).eq('client_order_id',order.clientOrderId));return;
 }
 const stamp=new Date(now()).toISOString(),s=order.signal;
 const existing=await checked(sb.from('plan_b_real_trades').select('status,filled_at,dispatch_started_at').eq('signal_id',s.id).maybeSingle());
 if(existing?.status==='closed')return;
 const filledAt=existing?.filled_at||(Number.isFinite(fill.filledAt)&&fill.filledAt>0?new Date(fill.filledAt).toISOString():stamp);
 await checked(sb.from('plan_b_real_trades').upsert({signal_id:s.id,symbol:order.symbol,side:order.side,status:'open',entry_price:fill.price,quantity:fill.quantity,leverage:order.leverage,margin_usd:fill.price*fill.quantity/order.leverage,client_order_id:order.clientOrderId,bingx_order_id:fill.orderId,signal_confirmed_at:s.confirmed_at,dispatch_started_at:existing?.dispatch_started_at||stamp,filled_at:filledAt},{onConflict:'signal_id'}));
 await checked(sb.from('plan_b_signals').update({dispatched_at:stamp}).eq('id',s.id));
 await checked(sb.from('plan_b_execution_intents').update({status:fill.status==='filled'?'open':'partial',fill_quantity:fill.quantity,fill_price:fill.price,order_id:fill.orderId,updated_at:stamp}).eq('client_order_id',order.clientOrderId));
}
export async function reconcileEntries({sb,bx,now=Date.now}){
 const rows=await checked(sb.from('plan_b_execution_intents').select('*,plan_b_signals!inner(*)').in('status',['submitted','unknown','partial','reserved']))||[];
 const errors=[];
 for(const i of rows){try{
  if(i.status==='reserved'){
   if(Date.parse(i.plan_b_signals.entry_deadline)<=now())await checked(sb.from('plan_b_execution_intents').update({status:'expired'}).eq('id',i.id).eq('status','reserved'));
   continue;
  }
  const order={plan:'B',symbol:i.symbol,side:i.side,quantity:Number(i.quantity),leverage:Number(i.plan_b_signals.leverage),clientOrderId:i.client_order_id,signal:i.plan_b_signals};
  const fill=await bx.lookup(order);
  // A timeout followed by NOT_FOUND is not proof no order can arrive; retain its reservation.
  if(fill.status!=='not_found')await recordEntry({sb,order,fill,now});
 }catch(error){errors.push({signal_id:i.signal_id,error:String(error.message)});}
 }
 return errors;
}
export async function closeDue({sb,bx,now=Date.now}){
 // Exit management deliberately does not depend on the new-entry switch or paper mode.
 const trades=await checked(sb.from('plan_b_real_trades').select('*,plan_b_signals!inner(expires_at)').eq('status','open'))||[];
 const results=[];
 for(const trade of trades){try{
  if(Date.parse(trade.plan_b_signals.expires_at)>now())continue;
  if(!trade.bingx_order_id){results.push({id:trade.id,error:'unverified trade; no synthetic close'});continue;}
  const intent=await checked(sb.from('plan_b_execution_intents').select('*').eq('signal_id',trade.signal_id).single());
  if(!['open','closing'].includes(intent.status)){results.push({id:trade.id,error:'entry reconciliation pending'});continue;}
  if(intent.status==='closing'){
   if(!intent.close_client_order_id)throw Error('legacy close requires reconciliation');
   const confirmation=await bx.lookup({symbol:trade.symbol,clientOrderId:intent.close_client_order_id});
   if(!confirmation.terminal&&confirmation.status!=='rejected'){results.push({id:trade.id,status:'close_pending'});continue;}
  }
  let quantity=positionQuantity(await bx.read('/openApi/swap/v2/user/positions',{symbol:trade.symbol+'-USDT'}),trade.symbol,trade.side);
  if(quantity>0){
   if(quantity>Number(trade.quantity)+1e-10)throw Error('untracked position quantity; close blocked');
   if(!['open','closing'].includes(intent.status)){results.push({id:trade.id,error:'entry reconciliation pending'});continue;}
   if(intent.status==='closing'){
    if(!intent.close_client_order_id)throw Error('legacy close requires reconciliation');
    const prior=await bx.lookup({symbol:trade.symbol,clientOrderId:intent.close_client_order_id});
    if(!prior.terminal&&prior.status!=='rejected'){results.push({id:trade.id,status:'close_pending'});continue;}
    quantity=positionQuantity(await bx.read('/openApi/swap/v2/user/positions',{symbol:trade.symbol+'-USDT'}),trade.symbol,trade.side);
    if(quantity===0)continue; // finalize on the next zero-position observation
    if(quantity>Number(trade.quantity)+1e-10)throw Error('untracked residual quantity');
   }
   const attempt=Number(intent.close_attempt||0)+1,clientOrderId=trade.client_order_id+'-c'+attempt;
   const claimed=await checked(sb.from('plan_b_execution_intents').update({status:'closing',close_attempt:attempt,close_client_order_id:clientOrderId,close_quantity:quantity,updated_at:new Date(now()).toISOString()}).eq('id',intent.id).eq('status',intent.status).eq('close_attempt',Number(intent.close_attempt||0)).select('id'));
   if(!claimed?.length)continue;
   const order={plan:'B',symbol:trade.symbol,side:trade.side,quantity,clientOrderId,close:true};
   const known=await bx.lookup(order),confirmation=known.status==='not_found'?await bx.submit(order):known;
   if(!confirmation.terminal&&confirmation.status!=='rejected'){results.push({id:trade.id,status:'close_pending'});continue;}
   const remaining=positionQuantity(await bx.read('/openApi/swap/v2/user/positions',{symbol:trade.symbol+'-USDT'}),trade.symbol,trade.side);
   if(remaining>0){results.push({id:trade.id,status:'close_pending',remaining});continue;}
  }
  await checked(sb.from('plan_b_real_trades').update({status:'closed',net_pnl_usd:null,closed_at:new Date(now()).toISOString(),updated_at:new Date(now()).toISOString()}).eq('id',trade.id));
  await checked(sb.from('plan_b_signals').update({status:'closed'}).eq('id',trade.signal_id));
  await checked(sb.from('plan_b_execution_intents').update({status:'closed'}).eq('id',intent.id));
  results.push({id:trade.id,status:'closed',settlement:'pending_exchange_history'});
 }catch(error){results.push({id:trade.id,error:String(error.message)});}
 }
 const unsettled=await checked(sb.from('plan_b_real_trades').select('*').eq('status','closed').is('net_pnl_usd',null).not('bingx_order_id','is',null))||[];
 for(const trade of unsettled){
  const raw=await bx.read('/openApi/swap/v1/trade/positionHistory',{symbol:trade.symbol+'-USDT',startTime:Date.parse(trade.created_at)-120000,endTime:now(),pageIndex:1,pageSize:100});
  const settled=historySettlement(raw,trade);if(settled)await checked(sb.from('plan_b_real_trades').update({...settled,updated_at:new Date(now()).toISOString()}).eq('id',trade.id));
 }
 return {ok:results.every(r=>!r.error),results};
}

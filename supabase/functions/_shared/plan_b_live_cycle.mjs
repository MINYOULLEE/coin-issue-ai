import {allocatePlanB,PLAN_B_STANDARD as STANDARD} from './plan_b_sizing.mjs';
import {constrainBQuantity} from './plan_b_exchange.mjs';
import {advanceProfitLock,normalizeHourlyKlines,normalizeKlines,profitFloorBreached,profitLockPolicy} from './plan_b_profit_lock.mjs';

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
function epochMs(value){const n=Number(value);return Number.isFinite(n)&&n>0?(n<100000000000?n*1000:n):NaN;}
function historyRows(raw){
 if(Array.isArray(raw))return raw;
 for(const key of ['list','positionHistory','positions','items','data'])if(Array.isArray(raw?.[key]))return raw[key];
 return [];
}
function presentNumber(row,keys){for(const key of keys)if(row?.[key]!=null&&Number.isFinite(Number(row[key])))return Number(row[key]);return null;}
export function historySettlement(raw,trade) {
 const rows=historyRows(raw);
 const opened=Date.parse(trade.filled_at||trade.created_at);
 const matches=rows.filter(p=>{
  const symbol=String(p.symbol||'').toUpperCase().replace('/','-'),normalized=symbol.includes('-')?symbol:symbol.endsWith('USDT')?symbol.slice(0,-4)+'-USDT':symbol;
  const rawSide=String(p.positionSide??p.side??p.direction??'').toUpperCase();
  const side=rawSide.includes('SHORT')||rawSide.includes('SELL')?'short':rawSide.includes('LONG')||rawSide.includes('BUY')?'long':Number(p.positionAmt??p.positionAmount??p.amount)<0?'short':'long';
  const openAt=epochMs(p.openTime??p.positionTime??p.createTime??p.time),closeAt=epochMs(p.closeTime??p.updateTime??p.endTime);
  return normalized===trade.symbol+'-USDT'&&side===trade.side&&Math.abs(openAt-opened)<=120000&&closeAt>opened;
 });
 if(matches.length!==1)return null;
 const p=matches[0],net=presentNumber(p,['netProfit','realizedProfit','realisedProfit','realizedPnl']),price=presentNumber(p,['avgClosePrice','closeAvgPrice','closePrice']);
 // Missing netProfit is not zero: do not guess whether a gross field includes funding.
 if(net==null||price==null||price<=0)return null;
 // BingX positionHistory can expose the settlement fee as positionCommission.
 const fee=presentNumber(p,['positionCommission','commission','tradingFee','fee']),closedAt=epochMs(p.closeTime??p.updateTime??p.endTime);
 return {net_pnl_usd:net,close_price:price,fee_usd:fee==null?null:Math.abs(fee),closed_at:new Date(closedAt).toISOString()};
}
export async function executeBatch({sb,bx,now=Date.now}) {
 const state=await checked(sb.from('plan_b_trading_state').select('*').eq('id','singleton').single());
 if(state.strategy_id!==STANDARD.strategy_id)throw Error('B strategy mismatch');
 if(!state.enabled||state.test_mode)return {mode:'paused',processed:0}; // never create paper real-trades
 const intents=await checked(sb.from('plan_b_execution_intents').select('*').not('status','in','(closed,rejected,expired)'))||[];
 // All uncertain submissions must be reconciled before allocating additional funds.
 if(intents.some(i=>['submitted','unknown','partial','closing'].includes(i.status)))return {mode:'reconciliation_required',processed:0};
 const balanceRaw=await bx.read('/openApi/swap/v3/user/balance',{}),balances=Array.isArray(balanceRaw)?balanceRaw:Array.isArray(balanceRaw?.balance)?balanceRaw.balance:[balanceRaw?.balance||balanceRaw];
 const account=balances.find(b=>b.asset==='USDT');if(!account)throw Error('USDT unavailable');
 const balance=Number(account.balance),equity=Number(account.equity),free=Number(account.availableMargin);
 if(![balance,equity,free].every(Number.isFinite))throw Error('invalid balance');
 const risk=await checked(sb.rpc('plan_b_update_risk_guard',{p_equity:equity,p_now:new Date(now()).toISOString()}));
 if(!risk?.entry_allowed)return {mode:'risk_pause',processed:0,risk};
 const pending=await checked(sb.from('plan_b_signals').select('*').eq('status','active').is('dispatched_at',null).gt('entry_deadline',new Date(now()).toISOString()).order('id'))||[];
 const occupied=new Set(intents.map(i=>i.symbol)),seen=new Set();
 const signals=selectExecutionGroup(pending.filter(s=>{if(!eligible(s,now())||occupied.has(s.symbol)||seen.has(s.symbol))return false;seen.add(s.symbol);return true;}),intents);
 if(!signals.length)return {mode:'live',processed:0};
 const livePositions=await bx.read('/openApi/swap/v2/user/positions',{});
 const liveRows=Array.isArray(livePositions)?livePositions:livePositions?.positions;
 if(!Array.isArray(liveRows))throw Error('invalid position response');
 for(const p of liveRows){const q=Number(p.positionAmt??p.positionAmount);if(!Number.isFinite(q))throw Error('invalid position quantity');}
 const ledgerOpen=await checked(sb.from('plan_b_real_trades').select('symbol,side,quantity').eq('status','open'))||[];
 const contracts=await bx.read('/openApi/swap/v2/quote/contracts',{});
 const proposals=[];
 for(const signal of signals){
  const exchangeQty=positionQuantity(liveRows,signal.symbol,signal.side),ownedQty=ledgerOpen.filter(t=>t.symbol===signal.symbol&&t.side===signal.side).reduce((n,t)=>n+Number(t.quantity||0),0);
  if(exchangeQty>ownedQty+1e-10)continue; // manual same-symbol+side position: never merge ownership
  // Configuration failure aborts the batch. No order may use an unverified leverage.
  const capabilities=await bx.verifyConfiguration(signal.symbol,Number(signal.leverage));
  const marks=await bx.read('/openApi/swap/v2/quote/premiumIndex',{symbol:signal.symbol+'-USDT'}),price=Number((Array.isArray(marks)?marks[0]:marks)?.markPrice);
  const adverse=(price/Number(signal.signal_price)-1)*100*(signal.side==='long'?1:-1);
  if(!Number.isFinite(adverse)||adverse>.35)continue;
  proposals.push({symbol:signal.symbol,entryPrice:price,signal,capabilities});
 }
 if(!proposals.length)return {mode:'live',processed:0};
 const snapshot=new Date(now()).toISOString();
 const held=intents.reduce((s,i)=>s+Number(i.reserved_usd),0);
 const currentGross=liveRows.reduce((sum,p)=>{const q=Math.abs(Number(p.positionAmt??p.positionAmount));const mark=Number(p.markPrice??p.avgPrice??p.entryPrice);return sum+(Number.isFinite(q)&&Number.isFinite(mark)?q*mark:0);},0);
 const allocation=allocatePlanB({plan:'B',strategyId:STANDARD.strategy_id,balance,equity,reservedMargin:held,currentGross,proposals});
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
 const policy=profitLockPolicy({symbol:order.symbol,side:order.side,entryPrice:fill.price,atr:Number(s.strategy_params?.atr_24)});
 await checked(sb.from('plan_b_real_trades').upsert({signal_id:s.id,symbol:order.symbol,side:order.side,status:'open',entry_price:fill.price,quantity:fill.quantity,leverage:order.leverage,margin_usd:fill.price*fill.quantity/order.leverage,client_order_id:order.clientOrderId,bingx_order_id:fill.orderId,signal_confirmed_at:s.confirmed_at,dispatch_started_at:existing?.dispatch_started_at||stamp,filled_at:filledAt,profit_lock_policy:policy?.policy||null,profit_lock_trigger_pct:policy?.triggerPct||null,profit_lock_keep_fraction:policy?.keepFraction||null},{onConflict:'signal_id'}));
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
 const trades=await checked(sb.from('plan_b_real_trades').select('*,plan_b_signals!inner(expires_at,strategy_id,strategy_params)').eq('status','open'))||[];
 const results=[];
 for(const trade of trades){try{
  let protectionDue=false;
  if(trade.plan_b_signals.strategy_id===STANDARD.strategy_id&&trade.profit_lock_policy){
   const raw=await bx.read('/openApi/swap/v3/quote/klines',{symbol:trade.symbol+'-USDT',interval:'1h',limit:3});
   const completed=normalizeHourlyKlines(raw,now()).filter(c=>c.t>=Math.floor(Date.parse(trade.filled_at)/3600000)*3600000);
   const latest=completed.at(-1),update=latest?advanceProfitLock(trade,latest):null;
   if(update){await checked(sb.from('plan_b_real_trades').update({...update,updated_at:new Date(now()).toISOString()}).eq('id',trade.id));Object.assign(trade,update);}
   if(trade.profit_lock_armed_at){
    const marks=await bx.read('/openApi/swap/v2/quote/premiumIndex',{symbol:trade.symbol+'-USDT'}),mark=Number((Array.isArray(marks)?marks[0]:marks)?.markPrice);
    const minuteRaw=await bx.read('/openApi/swap/v3/quote/klines',{symbol:trade.symbol+'-USDT',interval:'1m',limit:2});
    protectionDue=profitFloorBreached(trade,mark,now(),normalizeKlines(minuteRaw,60000,now()));
   }
  }
  const scheduledDue=Date.parse(trade.plan_b_signals.expires_at)<=now();
  if(!scheduledDue&&!protectionDue)continue;
  const exitReason=protectionDue?'profit_lock':'scheduled_time';
  if(!trade.bingx_order_id){results.push({id:trade.id,error:'unverified trade; no synthetic close'});continue;}
  const intent=await checked(sb.from('plan_b_execution_intents').select('*').eq('signal_id',trade.signal_id).single());
  if(!['open','closing'].includes(intent.status)){results.push({id:trade.id,error:'entry reconciliation pending'});continue;}
  if(intent.status==='closing'){
   if(!intent.close_client_order_id)throw Error('legacy close requires reconciliation');
   const confirmation=await bx.lookup({symbol:trade.symbol,clientOrderId:intent.close_client_order_id});
   if(!confirmation.terminal&&confirmation.status!=='rejected'){results.push({id:trade.id,status:'close_pending'});continue;}
  }
  let quantity=positionQuantity(await bx.read('/openApi/swap/v2/user/positions',{symbol:trade.symbol+'-USDT'}),trade.symbol,trade.side),manualRemainder=Number(intent.manual_remainder_qty??Math.max(0,quantity-Number(trade.quantity)));
  if(quantity>0){
   quantity=Math.min(quantity,Number(trade.quantity));
   if(!['open','closing'].includes(intent.status)){results.push({id:trade.id,error:'entry reconciliation pending'});continue;}
   if(intent.status==='closing'){
    if(!intent.close_client_order_id)throw Error('legacy close requires reconciliation');
    const prior=await bx.lookup({symbol:trade.symbol,clientOrderId:intent.close_client_order_id});
    if(!prior.terminal&&prior.status!=='rejected'){results.push({id:trade.id,status:'close_pending'});continue;}
    const observed=positionQuantity(await bx.read('/openApi/swap/v2/user/positions',{symbol:trade.symbol+'-USDT'}),trade.symbol,trade.side);
    if(observed<=manualRemainder+1e-10)quantity=0;else quantity=Math.min(observed-manualRemainder,Number(trade.quantity));
    if(quantity===0)continue; // finalize after owned quantity is gone; manual remainder is preserved
   }
   const attempt=Number(intent.close_attempt||0)+1,clientOrderId=trade.client_order_id+'-c'+attempt;
   const claimed=await checked(sb.from('plan_b_execution_intents').update({status:'closing',close_attempt:attempt,close_client_order_id:clientOrderId,close_quantity:quantity,manual_remainder_qty:manualRemainder,updated_at:new Date(now()).toISOString()}).eq('id',intent.id).eq('status',intent.status).eq('close_attempt',Number(intent.close_attempt||0)).select('id'));
   if(!claimed?.length)continue;
   await checked(sb.from('plan_b_real_trades').update({exit_reason:trade.exit_reason||exitReason,updated_at:new Date(now()).toISOString()}).eq('id',trade.id));
   const order={plan:'B',symbol:trade.symbol,side:trade.side,quantity,clientOrderId,close:true};
   const known=await bx.lookup(order),confirmation=known.status==='not_found'?await bx.submit(order):known;
   if(!confirmation.terminal&&confirmation.status!=='rejected'){results.push({id:trade.id,status:'close_pending'});continue;}
   const remaining=positionQuantity(await bx.read('/openApi/swap/v2/user/positions',{symbol:trade.symbol+'-USDT'}),trade.symbol,trade.side);
   if(remaining>manualRemainder+1e-10){results.push({id:trade.id,status:'close_pending',remaining_owned:remaining-manualRemainder});continue;}
  }
  await checked(sb.from('plan_b_real_trades').update({status:'closed',exit_reason:trade.exit_reason||exitReason,net_pnl_usd:null,closed_at:new Date(now()).toISOString(),updated_at:new Date(now()).toISOString()}).eq('id',trade.id));
  await checked(sb.from('plan_b_signals').update({status:'closed'}).eq('id',trade.signal_id));
  await checked(sb.from('plan_b_execution_intents').update({status:'closed'}).eq('id',intent.id));
  results.push({id:trade.id,status:'closed',settlement:'pending_exchange_history'});
 }catch(error){results.push({id:trade.id,error:String(error.message)});}
 }
 // BingX v1 positionHistory requires page/limit rather than pageIndex/pageSize.
 const unsettled=await checked(sb.from('plan_b_real_trades').select('*').eq('status','closed').is('net_pnl_usd',null).not('bingx_order_id','is',null))||[];
 for(const trade of unsettled){try{
  const raw=await bx.read('/openApi/swap/v1/trade/positionHistory',{symbol:trade.symbol+'-USDT',startTs:Date.parse(trade.created_at)-120000,endTs:now(),page:1,limit:100});
  const settled=historySettlement(raw,trade);if(settled)await checked(sb.from('plan_b_real_trades').update({...settled,updated_at:new Date(now()).toISOString()}).eq('id',trade.id));
 }catch(error){results.push({id:trade.id,error:'settlement lookup failed: '+String(error.message)});}}
 return {ok:results.every(r=>!r.error),results};
}

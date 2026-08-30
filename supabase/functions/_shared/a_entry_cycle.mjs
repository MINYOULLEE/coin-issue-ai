// A-only durable entry lifecycle. Recovery never submits or closes an order.
export function createAEntryCycle({db,signed,now=()=>new Date().toISOString()}) {
 const patch=(id,v)=>db(`trade_execution_reservations?signal_id=eq.${id}`,{method:'PATCH',body:JSON.stringify({...v,updated_at:now()})});
 const release=id=>db(`trade_execution_reservations?signal_id=eq.${id}`,{method:'DELETE'});
 async function invalid(id,message){await db(`trade_signals?id=eq.${id}`,{method:'PATCH',body:JSON.stringify({status:'invalidated',close_reason:message,closed_at:now(),updated_at:now()})});}
 async function settle(p,raw){
  const s=p.signal,id=Number(s.id),o=raw?.order??raw??{},qty=Number(o.executedQty),price=Number(o.avgPrice),status=String(o.status||'').toUpperCase();
  const orderId=o.orderID??o.orderId;
  if(typeof orderId==='number'&&!Number.isSafeInteger(orderId))throw Error('unsafe order id');
  const terminal=['FILLED','CANCELED','EXPIRED','REJECTED'].includes(status);
  if(terminal&&qty===0&&status!=='FILLED'){await invalid(id,`거래소 주문 ${status} · 체결 0`);await release(id);return {ok:false,rejected:true,signal_id:id};}
  if(!orderId||!Number.isFinite(qty)||qty<=0||qty>Number(p.quantity)||!Number.isFinite(price)||price<=0){await patch(id,{execution_status:'unknown'});return {ok:true,pending:true,signal_id:id};}
  const existing=(await db(`real_trades?signal_id=eq.${id}&select=id,status,entry_submitted_at,entry_filled_at`))?.[0];
  if(existing?.status==='closed'){if(terminal)await release(id);return {ok:true,signal_id:id,already_closed:true};}
  const stamp=now(),notional=qty*price,margin=notional/Number(p.leverage),fee=notional*Number(p.fee_rate||.001);
  const record={signal_id:id,symbol:s.symbol,bingx_symbol:p.symbol,side:s.side,signal_type:s.signal_type,status:'open',test_mode:false,margin_usd:margin,
   leverage:Number(p.leverage),notional_usd:notional,quantity:qty,entry_price:price,stop_price:null,target_price:null,bingx_order_id:String(orderId),
   strategy_epoch:s.strategy_epoch,collector_version:Number(s.collector_version||0),executor_version:Number(p.executor_version),signal_model_version:s.signal_model_version,
   signal_price:Number(p.signal_price),submitted_price:Number(p.signal_price),slippage_pct:(price/Number(p.signal_price)-1)*100*(s.side==='long'?1:-1),
   entry_submitted_at:existing?.entry_submitted_at||p.submitted_at||stamp,entry_filled_at:existing?.entry_filled_at||stamp,expected_fee_usd:fee,
   strategy_config:{daily_rebalance:true,exposure_multiplier:p.exposure_multiplier,max_gross_exposure:p.max_gross_exposure}};
  if(existing)await db(`real_trades?id=eq.${existing.id}&status=eq.open`,{method:'PATCH',body:JSON.stringify(record)});
  else await db('real_trades?on_conflict=signal_id',{method:'POST',headers:{Prefer:'resolution=ignore-duplicates,return=minimal'},body:JSON.stringify(record)});
  await db(`trade_signals?id=eq.${id}`,{method:'PATCH',body:JSON.stringify({account_equity_usd:Number(p.equity),margin_usd:margin,leverage:Number(p.leverage),notional_usd:notional,fee_usd:fee,updated_at:stamp})});
  if(terminal)await release(id);else await patch(id,{execution_status:'partial'});
  return {ok:true,pending:!terminal,signal_id:id,order_id:String(orderId),quantity:qty,fill_price:price};
 }
 async function recover(){
  const rows=await db('trade_execution_reservations?request_payload=not.is.null&select=signal_id,request_payload&order=created_at.asc');const results=[],errors=[];
  for(const row of rows||[])try{const p=row.request_payload;const raw=await signed('GET','/openApi/swap/v2/trade/order',{symbol:p.symbol,clientOrderId:`ciai${row.signal_id}`,recvWindow:5000});results.push(await settle(p,raw));}
  catch(e){errors.push({signal_id:row.signal_id,error:String(e.message)});await patch(row.signal_id,{execution_status:'unknown',last_error:String(e.message).slice(0,500)});}
  return {ok:errors.length===0,mode:'entry_recovery',results,errors};
 }
 async function submit(p){
  const s=p.signal||{},id=Number(s.id);let reserved=false,possible=false;
  if(s.signal_type!=='answer_mdd30'||!['BTC','ETH','XRP','TRX','SOL'].includes(s.symbol)||p.symbol!==s.symbol+'-USDT'||!['long','short'].includes(s.side)||p.side!==(s.side==='long'?'BUY':'SELL')||p.positionSide!==s.side.toUpperCase()||Number(p.leverage)!==10||!Number.isFinite(Number(p.quantity))||Number(p.quantity)<=0||!Number.isSafeInteger(id))throw Error('invalid A entry');
  try{
   const slot=await db('rpc/reserve_real_trade_slot',{method:'POST',body:JSON.stringify({p_signal_id:id,p_symbol:s.symbol,p_side:s.side,p_max_concurrent:Number(p.max_concurrent_positions),p_max_same_direction:Number(p.max_same_direction)})});
   if(!slot?.reserved)return {ok:true,pending:true,signal_id:id,reason:slot?.reason};reserved=true;
   const state=(await db('real_trading_state?id=eq.singleton&select=enabled,test_mode'))?.[0];
   if(!state?.enabled||state.test_mode)throw Error('A new entries disabled');
   await signed('POST','/openApi/swap/v2/trade/leverage',{symbol:p.symbol,side:p.positionSide,leverage:10,recvWindow:5000});
   const payload={...p,submitted_at:now()};
   // Persist BEFORE sending. A timeout/worker crash must never release this reservation by age.
   await patch(id,{request_payload:payload,execution_status:'submitted'});possible=true;
   const latest=(await db('real_trading_state?id=eq.singleton&select=enabled,test_mode'))?.[0];
   if(!latest?.enabled||latest.test_mode){possible=false;throw Error('A new entries disabled before submit');}
   const raw=await signed('POST','/openApi/swap/v2/trade/order',{symbol:p.symbol,side:p.side,positionSide:p.positionSide,type:'MARKET',quantity:p.quantity,clientOrderId:`ciai${id}`,recvWindow:5000});
   return await settle(payload,raw);
  }catch(e){
   if(possible){await patch(id,{execution_status:'unknown',last_error:String(e.message).slice(0,500)});return {ok:false,pending:true,signal_id:id,error:String(e.message)};}
   if(reserved){await invalid(id,`진입 전 실패: ${String(e.message).slice(0,400)}`);await release(id);}
   throw e;
  }
 }
 return {submit,recover,settle};
}

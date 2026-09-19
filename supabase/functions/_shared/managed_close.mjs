// Only the injected account-scoped adapter can read/write exchange or ledger state.
export async function closeManagedTrade({trade, position, lookup, submit, cancelStop, claim, save, finish}) {
 const quantity=Number(trade.quantity);
 if(!Number.isFinite(quantity)||quantity<=0)throw Error('invalid owned close quantity');
 const actual=await position();
 if(!Number.isFinite(actual)||actual<0)throw Error('invalid exchange close quantity');
 let context=trade.close_context;
 if(trade.status==='closing'&&!context)throw Error('legacy close requires reconciliation');
 let remaining,prior=null;
 if(context){
  if(!context.clientOrderId||!Number.isFinite(context.manualRemainder)||context.manualRemainder<0||!Number.isFinite(context.quantity)||context.quantity<=0)throw Error('invalid close context');
  // Even a zero position does not prove that an outstanding close order is terminal.
  prior=await lookup(context.clientOrderId);
  const status=String(prior?.status||'').toUpperCase();
  if(!['FILLED','CANCELED','CANCELLED','REJECTED','EXPIRED'].includes(status))throw Error('close confirmation pending');
  remaining=Math.max(0,actual-context.manualRemainder);
  if(remaining>quantity+1e-10)throw Error('position grew during close; ownership reconciliation required');
  if(remaining<=1e-10){await finish();return {closed:true};}
  const filled=Number(prior.executedQty);
  if(!Number.isFinite(filled)||filled<0||filled>context.quantity+1e-10)throw Error('invalid confirmed close fill');
  if(remaining>context.quantity-filled+1e-10)throw Error('close fill and position disagree; await reconciliation');
 }else{
  if(actual===0){await finish();return {closed:true};}
  remaining=Math.min(actual,quantity);
 }
 const attempt=Number(context?.attempt||0)+1;
 const next={attempt,clientOrderId:`mc${trade.id}c${attempt}`,submittedAt:Date.now(),quantity:remaining,
  manualRemainder:context?.manualRemainder??Math.max(0,actual-quantity)};
 if(!context)await cancelStop();
 if(!await claim(context??null,next))throw Error('close claimed by another invocation');
 // Claim is durable before submission. Uncertain attempts
 // remain closing and are lookup-only on subsequent runs (including NOT_FOUND).
 await submit(next.clientOrderId,next.quantity);
 const order=await lookup(next.clientOrderId);
 const status=String(order?.status||'').toUpperCase(),filled=Number(order?.executedQty);
 const after=await position();
 if(!Number.isFinite(after)||after<0)throw Error('invalid exchange close quantity');
 if(status!=='FILLED'||!Number.isFinite(filled)||filled<next.quantity-1e-10||after>next.manualRemainder+1e-10){
  await save('close confirmation pending');
  throw Error('close confirmation pending');
 }
 // Do not manufacture realized PnL from a mark or an estimated commission.
 await finish();return {closed:true};
}

export function managedCloseSettlement(raw,trade){
 if(Number(trade.close_context?.manualRemainder||0)>0)return null;
 const rows=Array.isArray(raw)?raw:raw?.list??raw?.positionHistory;
 if(!Array.isArray(rows))return null;
 const ms=v=>{const n=Number(v);return n>0?(n<1e11?n*1000:n):NaN};
 const matches=rows.filter(p=>p.symbol===trade.symbol+'-USDT'&&String(p.positionSide).toLowerCase()===trade.side&&
  Math.abs(ms(p.openTime??p.positionTime)-Date.parse(trade.opened_at))<=120000&&
  ms(p.closeTime??p.updateTime)>Date.parse(trade.opened_at)&&
  Math.abs(Math.abs(Number(p.closeAmount??p.positionAmt??p.closePositionAmt??p.quantity??p.amount))-Number(trade.quantity))<1e-10);
 if(matches.length!==1)return null;
 const p=matches[0],price=Number(p.avgClosePrice??p.closeAvgPrice),net=Number(p.netProfit),commission=Number(p.positionCommission??p.commission??p.fee);
 if(p.netProfit==null||!Number.isFinite(net)||!Number.isFinite(price)||price<=0)return null;
 return {price,net,fee:Number.isFinite(commission)?Math.abs(commission):null,closedAt:new Date(ms(p.closeTime??p.updateTime)).toISOString()};
}

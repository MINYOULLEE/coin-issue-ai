import standard from './plan_b_standard.json' with {type:'json'};
// Transport-independent lifecycle. Only mock adapters are exercised by this repo's
// tests. No exchange keys, HTTP calls or background scheduling in this module.
export async function processReservedOrder(order, {store,exchange,now=Date.now}) {
  if(order.plan!=='B'||!order.clientOrderId.startsWith(standard.isolation.client_order_prefix+'-'))throw Error('B identity required');
  if(!Number.isFinite(order.quantity)||order.quantity<=0)throw Error('invalid fixed quantity');
  // claim() must be an atomic DB transition; a timeout never frees a reservation.
  if(!await store.claim(order.clientOrderId))return {status:'already_claimed'};
  let observed;
  try {
    observed=await exchange.lookup(order.clientOrderId);
    if(observed.status==='not_found') {
      if(now()>=order.entryDeadline) {
        await store.finish(order.clientOrderId,{status:'expired',release:true});return {status:'expired'};
      }
      // Only a definitive NOT_FOUND is allowed to precede first submission.
      observed=await exchange.submit({...order});
    }
    if(observed.status==='filled'||observed.status==='partially_filled') {
      if(!Number.isFinite(observed.quantity)||observed.quantity<=0||observed.quantity>order.quantity||
         !Number.isFinite(observed.price)||observed.price<=0)throw Error('invalid fill');
      await store.finish(order.clientOrderId,{...observed,release:false});return observed;
    }
    if(observed.status==='rejected' && observed.quantity===0) {
      await store.finish(order.clientOrderId,{status:'rejected',release:true});return observed;
    }
    await store.finish(order.clientOrderId,{status:'unknown',release:false});return {status:'unknown'};
  }catch {
    await store.finish(order.clientOrderId,{status:'unknown',release:false});return {status:'unknown'};
  }
}

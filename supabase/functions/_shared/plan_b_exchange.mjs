import {createHmac} from 'node:crypto';
import standard from './plan_b_standard.json' with {type:'json'};
import runtime from './plan_b_runtime.json' with {type:'json'};
export function normalizeBOrder(data) {
 const d=data?.order||data||{},qty=Number(d.executedQty??d.cumQty),price=Number(d.avgPrice);
 const id=d.orderID??d.orderId;
 if(typeof id==='number'&&!Number.isSafeInteger(id))throw Error('unsafe order ID');
 if(!Number.isFinite(qty)||qty<0) return {status:'unknown'};
 const status=String(d.status||'').toUpperCase();
 if(qty>0 && Number.isFinite(price)&&price>0) return {status:['FILLED','CANCELED','EXPIRED'].includes(status)?'filled':'partially_filled',terminal:['FILLED','CANCELED','EXPIRED'].includes(status),quantity:qty,price,orderId:String(id||''),filledAt:Number(d.time??d.updateTime)};
 if(qty===0&&['CANCELED','EXPIRED','REJECTED'].includes(status))return {status:'rejected',quantity:0};
 return {status:'unknown'};
}
export function constrainBQuantity(order,contract,price) {
 if(!standard.symbols[order.symbol]||contract.symbol!==order.symbol+'-USDT')throw Error('B contract mismatch');
 const precision=Number(contract.quantityPrecision),minQty=Number(contract.tradeMinQuantity),minUSDT=Number(contract.tradeMinUSDT);
 if(!Number.isInteger(precision)||precision<0||precision>10||![minQty,minUSDT,price,order.quantity].every(Number.isFinite)||price<=0||minQty<=0||minUSDT<0)throw Error('invalid contract constraints');
 if(String(contract.apiStateOpen)!=='true'||String(contract.apiStateClose)!=='true'||Number(contract.status)!==1)throw Error('contract not available');
 const cap=Number(order.side==='long'?contract.maxLongLeverage:contract.maxShortLeverage);
 if(cap<order.leverage||!Number.isFinite(cap))throw Error('required leverage unavailable');
 const quantity=Math.floor(order.quantity*10**precision)/10**precision;
 if(quantity<=0||quantity>order.quantity||quantity<minQty||quantity*price<minUSDT)throw Error('below minimum order');
 return {...order,quantity,quantityText:quantity.toFixed(precision),notional:quantity*price,margin:quantity*price/order.leverage};
}
export function createBExchange({apiKey,secret,parse=JSON.parse,fetcher=fetch,liveAuthorized=()=>false,exitAuthorized=()=>false,configurationAuthorized=()=>false,sleep=ms=>new Promise(r=>setTimeout(r,ms))}) {
 if(!apiKey||!secret)throw Error('B credentials missing');
 const reads=new Set(['/openApi/swap/v3/user/balance','/openApi/swap/v2/user/positions','/openApi/swap/v2/quote/contracts','/openApi/swap/v2/quote/premiumIndex','/openApi/swap/v2/trade/order','/openApi/swap/v2/trade/openOrders','/openApi/swap/v2/trade/leverage','/openApi/swap/v2/trade/marginType','/openApi/swap/v1/positionSide/dual','/openApi/swap/v1/maintMarginRatio','/openApi/swap/v2/trade/fillHistory']);
 reads.add('/openApi/swap/v1/trade/positionHistory');
 const lastRead=new Map();
 async function request(method,path,params={},closing=false,attempt=0) {
  if(method==='GET'&&!reads.has(path))throw Error('unsupported B read endpoint');
  if(method!=='GET'){
   const config=path==='/openApi/swap/v2/trade/leverage' && method==='POST' && !runtime.live_ready && await configurationAuthorized();
   const order=path==='/openApi/swap/v2/trade/order' && (closing?await exitAuthorized():runtime.live_ready&&await liveAuthorized());
   if(!config&&!order)throw Error('B live transport locked');
  }
  if(method==='GET'){const wait=550-(Date.now()-(lastRead.get(path)||0));if(wait>0)await sleep(wait);lastRead.set(path,Date.now());}
  const all={...params,recvWindow:5000,timestamp:Date.now()};
  const query=Object.keys(all).sort().map(k=>k+'='+encodeURIComponent(String(all[k]))).join('&');
  const signature=createHmac('sha256',secret).update(query).digest('hex');
  const response=await fetcher('https://open-api.bingx.com'+path+(method==='GET'?'?'+query+'&signature='+signature:''),{
   method,headers:{'X-BX-APIKEY':apiKey,'Content-Type':'application/x-www-form-urlencoded'},
   body:method==='GET'?undefined:query+'&signature='+signature,signal:AbortSignal.timeout(8000)});
  const result=parse(await response.text());
  if(!response.ok||Number(result.code)!==0){
   // Reads may retry rate limits; order/configuration writes are NEVER blindly retried.
   if(method==='GET'&&Number(result.code)===100410&&attempt<2){await sleep(1000*2**attempt);return request(method,path,params,closing,attempt+1);}
   const e=Error('BingX request failed: '+String(result.code??response.status));e.code=Number(result.code);throw e;
  }
  return result.data;
 }
 return {read:(path,params)=>request('GET',path,params),
  async verifyConfiguration(symbol,leverage){
   const pair=symbol+'-USDT';
   const mode=await request('GET','/openApi/swap/v1/positionSide/dual');
   if(String(mode.dualSidePosition)!=='true')throw Error('B hedge mode required');
   const margin=await request('GET','/openApi/swap/v2/trade/marginType',{symbol:pair});
   if(margin.marginType!=='ISOLATED')throw Error('B isolated margin required');
   const lev=await request('GET','/openApi/swap/v2/trade/leverage',{symbol:pair});
   if(Number(lev.longLeverage)!==leverage||Number(lev.shortLeverage)!==leverage)throw Error(`B leverage mismatch: ${symbol}; expected=${leverage}, long=${lev.longLeverage}, short=${lev.shortLeverage}`);
   return {maxLongLeverage:lev.maxLongLeverage,maxShortLeverage:lev.maxShortLeverage};
  },
  async alignLeverage(symbol){
   const expected=standard.symbols[symbol]?.leverage,pair=symbol+'-USDT';
   if(!expected||runtime.live_ready||!await configurationAuthorized())throw Error('B configuration locked');
   const mode=await request('GET','/openApi/swap/v1/positionSide/dual');
   const margin=await request('GET','/openApi/swap/v2/trade/marginType',{symbol:pair});
   if(String(mode.dualSidePosition)!=='true'||margin.marginType!=='ISOLATED')throw Error('B mode requires manual review');
   const before=await request('GET','/openApi/swap/v2/trade/leverage',{symbol:pair});
   if(![before.longLeverage,before.shortLeverage,before.maxLongLeverage,before.maxShortLeverage].every(x=>Number.isFinite(Number(x))&&Number(x)>0))throw Error('invalid leverage response');
   if(Number(before.maxLongLeverage)<expected||Number(before.maxShortLeverage)<expected)throw Error('required leverage unavailable');
   for(const side of ['LONG','SHORT']){
    if(Number(before[side==='LONG'?'longLeverage':'shortLeverage'])===expected)continue;
    const positions=await request('GET','/openApi/swap/v2/user/positions',{symbol:pair});
    const rawOrders=await request('GET','/openApi/swap/v2/trade/openOrders',{symbol:pair});
    const orders=Array.isArray(rawOrders)?rawOrders:rawOrders?.orders;
    if(!Array.isArray(positions)||positions.some(p=>!Number.isFinite(Number(p.positionAmt))||Number(p.positionAmt)!==0)||!Array.isArray(orders)||orders.length)throw Error('B configuration requires no positions or open orders');
    await request('POST','/openApi/swap/v2/trade/leverage',{symbol:pair,side,leverage:expected});
    await sleep(600);
   }
   const after=await request('GET','/openApi/swap/v2/trade/leverage',{symbol:pair});
   if(Number(after.longLeverage)!==expected||Number(after.shortLeverage)!==expected)throw Error('B leverage verification failed');
   return {symbol,expected,before:{long:Number(before.longLeverage),short:Number(before.shortLeverage)},after:{long:Number(after.longLeverage),short:Number(after.shortLeverage)},orders_submitted:0};
  },
  async lookup(order){try{return normalizeBOrder(await request('GET','/openApi/swap/v2/trade/order',{symbol:order.symbol+'-USDT',clientOrderId:order.clientOrderId}));}catch(e){if(e.code===109421)return {status:'not_found'};throw e;}},
  async submit(order){if(order.plan!=='B'||!standard.symbols[order.symbol]||!(order.clientOrderId.startsWith(standard.isolation.client_order_prefix+'-')||(order.close&&order.clientOrderId.startsWith('pb16-')))||!['long','short'].includes(order.side))throw Error('invalid B order');
   const side=order.close?(order.side==='long'?'SELL':'BUY'):(order.side==='long'?'BUY':'SELL');
   return normalizeBOrder(await request('POST','/openApi/swap/v2/trade/order',{symbol:order.symbol+'-USDT',side,positionSide:order.side.toUpperCase(),type:'MARKET',quantity:order.quantity,clientOrderId:order.clientOrderId},order.close===true));
  }
 };
}

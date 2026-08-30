// Historical reproduction against pre-repair commit 50267e7. For current regression tests use test_a_entry_cycle.mjs.
const fs=require('node:fs'),vm=require('node:vm'),{stripTypeScriptTypes}=require('node:module'),{createHmac}=require('node:crypto');
const assert=require('node:assert/strict');
const src=require('node:child_process').execFileSync('git',['show','50267e7:supabase/functions/bingx-order-submit/index.ts'],{encoding:'utf8'}).replace(/^import .*;\r?$/gm,'');
async function scenario(kind){
 let handler;const events=[];
 const context={createHmac,JSONBig:()=>({parse:JSON.parse}),Response,AbortSignal,console,setTimeout:f=>{f();return 0;},Deno:{env:{get:k=>k==='SUPABASE_URL'?'https://db.invalid':'dummy'},serve:f=>handler=f},fetch:async(url,opt={})=>{
  const method=opt.method||'GET';events.push({method,url,body:opt.body});
  if(url.includes('/rest/v1/'))return Response.json(url.includes('reserve_real_trade_slot')?{reserved:true}:[]);
  if(url.includes('/trade/leverage'))return Response.json({code:0,data:{}});
  if(method==='POST'&&kind==='accepted_then_timeout')throw Error('simulated timeout after exchange accepts order');
  return Response.json({code:0,data:{orderID:'12345678901234567',status:'NEW',avgPrice:'0',executedQty:'0'}});
 }};
 vm.runInNewContext(stripTypeScriptTypes(src),context);
 const response=await handler({method:'POST',headers:new Headers({'x-internal-key':'dummy'}),json:async()=>({signal:{id:7,symbol:'BTC',side:'long',signal_type:'answer_mdd30'},symbol:'BTC-USDT',side:'BUY',positionSide:'LONG',leverage:10,quantity:.01,signal_price:100,max_concurrent_positions:5,max_same_direction:5,equity:150})});
 const body=await response.json();
 return {kind,status:response.status,body,orderLookups:events.filter(x=>x.method==='GET'&&x.url.includes('/trade/order')).length,reservationReleased:events.some(x=>x.method==='DELETE'&&x.url.includes('trade_execution_reservations')),recorded:events.filter(x=>x.url.endsWith('/real_trades')&&x.method==='POST').map(x=>JSON.parse(x.body))};
}
(async()=>{
 const timeout=await scenario('accepted_then_timeout');assert.equal(timeout.orderLookups,0);assert.equal(timeout.reservationReleased,true);
 const unfilled=await scenario('unfilled_order');assert.equal(unfilled.recorded[0].status,'open');assert.equal(unfilled.recorded[0].quantity,.01);
 console.log(JSON.stringify({findings_reproduced:true,timeout,unfilled},null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});

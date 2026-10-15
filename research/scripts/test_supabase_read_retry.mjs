import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {supabaseReadFetch} from '../../supabase/functions/_shared/supabase_read_retry.mjs';
const root='https://example.supabase.co', url=root+'/rest/v1/real_trades?select=id';
test('observed read 502 recovers without replaying delivery or changing result',async()=>{
 let calls=0;const logs=[],delays=[];
 const f=supabaseReadFetch(root,{fetchImpl:async()=>++calls===1?new Response('<html>502</html>',{status:502,headers:{'sb-request-id':'r1','cf-ray':'ray'}}):Response.json([{id:1}]),sleep:async ms=>delays.push(ms),onRetry:x=>logs.push(x)});
 assert.deepEqual(await(await f(url)).json(),[{id:1}]);assert.equal(calls,2);assert.deepEqual(delays,[250]);assert.equal(logs[0].request_id,'r1');assert.equal(logs[0].path,'/rest/v1/real_trades');
});
test('exact gateway project-routing response retries on safe reads only',async()=>{
 let n=0;const f=supabaseReadFetch(root,{fetchImpl:async()=>++n<3?new Response('Project not specified.',{status:400}):Response.json([]),sleep:async()=>{}});
 assert.equal((await f(url)).status,200);assert.equal(n,3);
});
test('persistent outage is returned, never replaced with successful empty data',async()=>{
 let n=0;const f=supabaseReadFetch(root,{fetchImpl:async()=>{n++;return new Response('bad gateway',{status:503})},sleep:async()=>{}});
 const r=await f(url);assert.equal(r.status,503);assert.equal(await r.text(),'bad gateway');assert.equal(n,3);
});
test('writes, RPC, function calls, external endpoints never retry',async()=>{
 for(const [u,method] of [[url,'POST'],[url,'PATCH'],[url,'DELETE'],[root+'/rest/v1/rpc/claim','GET'],[root+'/functions/v1/plan-b-executor','POST'],['https://api.telegram.org/sendMessage','POST'],['https://other.supabase.co/rest/v1/x','GET']]){
  let n=0;const f=supabaseReadFetch(root,{fetchImpl:async()=>{n++;return new Response('bad',{status:502})},sleep:async()=>{}});await f(u,{method});assert.equal(n,1,u);
 }
});
test('auth, application validation, throttling and server application errors are not retried',async()=>{
 for(const status of [400,401,403,404,429,500]){let n=0;const f=supabaseReadFetch(root,{fetchImpl:async()=>{n++;return new Response('validation error',{status})},sleep:async()=>{}});await f(url);assert.equal(n,1);}
});
test('network error is bounded; unknown errors and caller cancellation fail immediately',async()=>{
 let n=0;const f=supabaseReadFetch(root,{fetchImpl:async()=>{n++;throw new TypeError('network')},sleep:async()=>{}});await assert.rejects(()=>f(url),/network/);assert.equal(n,3);
 const c=new AbortController();c.abort(new Error('cancelled'));await assert.rejects(()=>f(url,{signal:c.signal}),/cancelled/);assert.equal(n,3);
});
test('Request methods and signal are respected; retry logs omit secrets and query data',async()=>{
 let n=0;const logs=[];const f=supabaseReadFetch(root,{fetchImpl:async()=>++n===1?new Response('bad',{status:502}):Response.json([]),sleep:async()=>{},onRetry:d=>logs.push(d)});
 await f(new Request(url+'&secret=never-log',{headers:{apikey:'never-log'}}));assert.equal(n,2);assert.ok(!JSON.stringify(logs).includes('never-log'));
 n=0;await f(new Request(url,{method:'PATCH',body:'{}'}));assert.equal(n,1);
});
test('only notifier database client is wrapped, not Telegram send or delivery markers',()=>{
 const s=readFileSync('supabase/functions/telegram-trade-notify/index.ts','utf8');assert.ok(s.includes('global:{fetch:supabaseReadFetch(URL'));
 assert.ok(s.includes('await markDelivered("real_trades",x.id,"telegram_close_notified_at")'));
 assert.ok(s.includes('await fetch(`https://api.telegram.org/'));
});

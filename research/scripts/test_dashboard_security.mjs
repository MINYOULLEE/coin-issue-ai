import test from 'node:test';
import assert from 'node:assert/strict';
import {createHmac} from 'node:crypto';
import fs from 'node:fs';
import {createDashboardSessions,reserveLoginAttempt} from '../../supabase/functions/_shared/dashboard_sessions.mjs';
import {allHistoryPages} from '../../supabase/functions/_shared/history_pages.mjs';
test('same password root cannot cross A/B session domains; old tokens rejected',()=>{
 const a=createDashboardSessions('A'),b=createDashboardSessions('B'),key='offline-test-key',now=1788170000000;
 const at=a.issue(key,now),bt=b.issue(key,now);
 assert.equal(a.valid(at,key,now),true);assert.equal(b.valid(bt,key,now),true);
 assert.equal(a.valid(bt,key,now),false);assert.equal(b.valid(at,key,now),false);
 const p=Buffer.from(JSON.stringify({plan:'B',exp:now+60000})).toString('base64url');const old=p+'.'+createHmac('sha256',key).update(p).digest('base64url');
 assert.equal(a.valid(old,key,now),false);assert.equal(b.valid(old,key,now),false);
 assert.equal(a.valid(at,key,now+14400000),false);assert.equal(a.valid(at+'.extra',key,now),false);
 assert.equal(a.valid(at+'x',key,now),false);assert.equal(a.valid(at,key,now-120000),false);
});
test('login limit buckets isolate plans and never contain raw client IP',async()=>{
 const inputs=[],req=new Request('https://example.test',{headers:{'x-forwarded-for':'192.0.2.1'}});
 const rpc=async p=>{inputs.push(p);return {allowed:false,retry_after:900}};
 for(const plan of ['A','B'])assert.equal((await reserveLoginAttempt(req,plan,'fixture',rpc)).allowed,false);
 assert.notEqual(inputs[0].p_key,inputs[1].p_key);assert.match(inputs[0].p_key,/^[a-f0-9]{64}$/);
 await assert.rejects(()=>reserveLoginAttempt(req,'B','fixture',async()=>{throw Error('database unavailable')}));
});
test('both entrypoints use DB login protection and scoped sessions',()=>{
 for(const [name,plan] of [['bingx-account-read','A'],['plan-b-account-read','B']]){
 const s=fs.readFileSync(`supabase/functions/${name}/index.ts`,'utf8');assert.ok(s.includes(`createDashboardSessions("${plan}")`));assert.ok(s.includes(`reserveLoginAttempt(req,"${plan}"`));assert.ok(s.includes('dashboard_login_attempt'));assert.ok(s.includes('planSessions.valid'));assert.ok(!s.includes('const attempts=new Map'));
 }
});
test('history aggregation includes all 2507 rows even with server page cap',async()=>{
 const input=Array.from({length:2507},(_,i)=>({external_id:String(i),realized_pnl_usd:1}));let calls=0;
 const rows=await allHistoryPages(async offset=>{calls++;return input.slice(offset,offset+200)});
 assert.equal(rows.length,2507);assert.equal(rows.reduce((n,r)=>n+r.realized_pnl_usd,0),2507);assert.equal(calls,14);
});
test('pagination failure or duplicates never become a partial successful total',async()=>{
 let calls=0;await assert.rejects(()=>allHistoryPages(async()=>{if(calls++)throw Error('DB down');return [{external_id:'1'}]}));
 await assert.rejects(()=>allHistoryPages(async()=>[{external_id:'same'}]),/changed/);
});

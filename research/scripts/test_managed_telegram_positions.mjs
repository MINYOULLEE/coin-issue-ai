import test from 'node:test';import assert from 'node:assert/strict';import fs from 'node:fs';import vm from 'node:vm';import {stripTypeScriptTypes} from 'node:module';
import {managedPositionSnapshot,managedPositionPages} from '../../supabase/functions/_shared/managed_telegram_positions.mjs';
const id='5821bee3-6825-4605-9bff-988414fc0313';
const position={symbol:'BTC-USDT',positionSide:'LONG',positionAmt:'1',leverage:'10',unrealizedProfit:'-263.34',initialMargin:'568.624487',markPrice:'82500',liquidationPrice:'78263.70'};
test('uses only requested account credentials and GET positions; strips unrelated response fields',async()=>{
 const seen=[];const r=await managedPositionSnapshot(id,{credentials:async scope=>{assert.equal(scope,id);return{api_key:'managed-only',secret_key:'private'}},fetchImpl:async(url,init)=>{seen.push(url);assert.match(url,/^https:\/\/open-api.bingx.com\/openApi\/swap\/v2\/user\/positions\?/);assert.equal(init.method,'GET');assert.equal(init.headers['X-BX-APIKEY'],'managed-only');return Response.json({code:0,data:[{...position,secret:'never-show'},{positionAmt:0}]})},now:()=>1000});
 assert.equal(r.ok,true);assert.equal(r.positions.length,1);assert.equal(r.checkedAt,'1970-01-01T00:00:01.000Z');assert.ok(!JSON.stringify(r).includes('never-show'));assert.equal(seen.length,1);
});
test('invalid IDs, missing managed keys and failed exchange never fall back to A/B keys or empty success',async()=>{
 let reads=0;const fetchImpl=async()=>{reads++;throw Error('secret-private-message')};
 const a=await managedPositionSnapshot('invalid',{credentials:async()=>{throw Error('must not run')},fetchImpl});assert.equal(a.ok,false);assert.equal(reads,0);
 const b=await managedPositionSnapshot(id,{credentials:async()=>({}),fetchImpl});assert.equal(b.ok,false);assert.equal(reads,0);
 const c=await managedPositionSnapshot(id,{credentials:async()=>({api_key:'k',secret_key:'s'}),fetchImpl});assert.equal(c.ok,false);assert.equal(c.positions,null);assert.ok(!JSON.stringify(c).includes('secret-private-message'));
});
test('bad response shape/quantity and exchange permission errors remain unavailable',async()=>{
 for(const body of [{code:100,data:[]},{code:0,data:{}},{code:0,data:[{positionAmt:'bad'}]},{code:0,data:[{positionAmt:null}]}]){
 const r=await managedPositionSnapshot(id,{credentials:async()=>({api_key:'k',secret_key:'s'}),fetchImpl:async()=>Response.json(body)});assert.equal(r.ok,false);}
});
test('renders screenshot fields including signed collateral ROI and liquidation distance',()=>{
 const text=managedPositionPages('header',{ok:true,positions:[position,{symbol:'LINK-USDT',positionSide:'SHORT',positionAmt:2,leverage:5,unrealizedProfit:3,initialMargin:10,markPrice:10,liquidationPrice:12}],checkedAt:'2026-10-16T05:00:00Z'}).join('\n');
 for(const pattern of [/BTC LONG · 10x/,/-263.34 USDT/ ,/-46.31%/,/78,263.70/,/거리 5.13%/,/LINK SHORT · 5x/,/\+30.00%/,/계정 전체\(수동 포함\)/,/2026-10-16 12:00:00/])assert.match(text,pattern);
});
test('confirmed empty differs from query failure and unknown liquidation/ROI is never zero',()=>{
 assert.match(managedPositionPages('header',{ok:true,positions:[],checkedAt:new Date().toISOString()})[0],/열린 포지션 없음/);
 const fail=managedPositionPages('header',{ok:false,error:'진행 포지션 조회 실패'})[0];assert.match(fail,/조회 실패/);assert.ok(!fail.includes('열린 포지션 없음'));
 const missing=managedPositionPages('header',{ok:true,positions:[{symbol:'X<&-USDT',positionAmt:1,positionSide:'LONG'}],checkedAt:new Date().toISOString()})[0];assert.match(missing,/조회 불가/);assert.match(missing,/X&lt;&amp;/);assert.ok(!missing.includes('0.00%'));
});
test('many positions are split below Telegram limit without losing positions',()=>{
 const positions=Array.from({length:80},(_,i)=>({...position,symbol:`COIN${i}-USDT`}));const pages=managedPositionPages('name and balances',{ok:true,positions,checkedAt:new Date().toISOString()},'footer');assert(pages.length>1);assert(pages.every(p=>p.length<=3800));for(let i=0;i<80;i++)assert.equal(pages.join('\n').split(`<b>COIN${i} LONG`).length-1,1);
});
test('actual overview renders current positions and balances per account; callback and owner gates remain',async()=>{
 const source=fs.readFileSync('supabase/functions/telegram-bot-webhook/index.ts','utf8'),code=source.split(/\r?\n/).find(l=>l.startsWith('async function managedOverview'));
 const messages=[];const accounts=[{id,display_name:'first',assigned_plan:'A',alerts_enabled:false},{id:'a9848c73-3c8e-45ae-b714-b9dfc102a4d6',display_name:'second',assigned_plan:'B',alerts_enabled:false}];
 const q={select(){return q},order:async()=>({data:accounts})};const ctx=vm.createContext({sb:{from:()=>q},managedPositionSnapshot:async account=>({ok:true,positions:account===id?[position]:[],checkedAt:new Date().toISOString()}),managedCredentials:()=>{},managedSettlements:async()=>[],managedBalanceText:()=> 'start realized equity',managedPositionPages,tg:async(method,body)=>{messages.push(body);return{}},send:()=>{}});
 vm.runInContext(stripTypeScriptTypes(code),ctx);await vm.runInContext("managedOverview('owner')",ctx);
 assert.equal(messages.length,2);assert.match(messages[0].text,/BTC LONG/);assert.ok(!messages[1].text.includes('BTC LONG'));assert.match(messages[1].text,/열린 포지션 없음/);assert(messages.every(x=>x.text.includes('알림 OFF')));assert.equal(messages[0].reply_markup.inline_keyboard[0][0].callback_data,'managed:'+id);
 assert.ok(source.includes('if(id!==CHAT)return Response.json({ok:true})'));assert.ok(source.includes('validWebhookSecret'));assert.ok(!code.includes('.update('));
});

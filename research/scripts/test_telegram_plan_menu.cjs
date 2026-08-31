const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {stripTypeScriptTypes}=require('node:module');
const webhook=fs.readFileSync('supabase/functions/telegram-bot-webhook/index.ts','utf8');
const notify=fs.readFileSync('supabase/functions/telegram-trade-notify/index.ts','utf8');
test('webhook and notification share the same six-button keyboard',()=>{
 const extract=s=>s.match(/const keyboard=(\{keyboard:.*?\});/)[1];
 // Webhook declares sb and keyboard on one line, but keyboard remains a const.
 assert.equal(extract(webhook),extract(notify));
});
test('A/B overview routes read isolated account/state and return actual status',async()=>{
 const sent=[],tables=[];
 const sb={from:t=>{tables.push(t);return {select:()=>({eq:()=>({single:async()=>({data:{enabled:true,test_mode:false}})})})}}};
 const context={Deno:{env:{get:()=> 'fixture'},serve:()=>{}},createClient:()=>sb,console,
 fetch:async(url,opt)=>{sent.push(JSON.parse(opt.body));return {json:async()=>({ok:true,result:{}})}}};
 vm.createContext(context);
 const code=stripTypeScriptTypes(webhook.replace(/^import .*;\r?\n/gm,''));
 vm.runInContext(code,context);
 vm.runInContext('account=async()=>({balance:100,equity:101,available:90,upnl:1,positions:[]});pbAccount=async()=>({balance:150,equity:152,available:140,upnl:2,positions:[]});',context);
 await context.answer('6818439075','🔵 A 현황');await context.answer('6818439075','🟣 B 현황');
 assert.deepEqual(tables,['real_trading_state','plan_b_trading_state']);
 assert.match(sent[0].text,/A플랜/);assert.match(sent[0].text,/100.00/);
 assert.match(sent[1].text,/B플랜/);assert.match(sent[1].text,/150.00/);assert.match(sent[1].text,/ON · LIVE/);
 await context.answer('6818439075','🔗 대시보드');assert.ok(sent[2].reply_markup.inline_keyboard);
});

const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {stripTypeScriptTypes}=require('node:module');
test('A/B delayed entries and already-closed fills get per-trade entry receipts',async()=>{
 const s=fs.readFileSync('supabase/functions/telegram-trade-notify/index.ts','utf8');
 for(const [label,table,last] of [['newRows','real_trades','lastId'],['newPbRows','plan_b_real_trades','lastPbId']]){
  const line=s.split('\n').find(x=>x.includes(`for(const x of ${label}`));const sent=[],marks=[];
  const ctx=vm.createContext({[label]:[{id:1,status:'pending'},{id:2,status:'closed',bingx_order_id:'fixture',entry_price:10,symbol:'ETH',side:'long',leverage:3,margin_usd:20},{id:3,status:'rejected',reject_reason:'fixture'}],[last]:100,send:async m=>sent.push(m),markDelivered:async(...x)=>marks.push(x),side:String,price:String,num:String,MDD30_STANDARD:'fixture'});
  await vm.runInContext('(async()=>{'+line+'})()',ctx);
  assert.equal(sent.length,2);assert.equal(marks[0][0],table);assert.equal(marks[0][2],'telegram_entry_notified_at');assert.equal(marks[1][2],'telegram_rejection_notified_at');
  const query=s.split('\n').find(x=>x.includes(`data:${label},`));assert.ok(query.includes('telegram_entry_notified_at.is.null'));assert.ok(!query.includes('.gt('));
 }
});
test('A close late settlement has no global timestamp cutoff and validates actual values',async()=>{
 const s=fs.readFileSync('supabase/functions/telegram-trade-notify/index.ts','utf8'),query=s.split('\n').find(x=>x.includes('data:closed,error:e2'));
 assert.ok(query.includes('telegram_close_notified_at'));assert.ok(!query.includes('.gt('));
 const line=s.split('\n').find(x=>x.includes('for(const x of closed||[]')),sent=[],marks=[];
 const ctx=vm.createContext({closed:[{id:1,net_pnl_usd:0,close_price:10,closed_at:'2020-01-01',margin_usd:10},{id:2,net_pnl_usd:null,close_price:10}],lastClosed:'2026-08-31',send:async m=>sent.push(m),markDelivered:async(...x)=>marks.push(x),side:String,price:String,num:String});
 await vm.runInContext('(async()=>{'+line+'})()',ctx);assert.equal(sent.length,1);assert.equal(marks[0][2],'telegram_close_notified_at');
});
test('B late settlement delivery does not use a close-time watermark',async()=>{
 const s=fs.readFileSync('supabase/functions/telegram-trade-notify/index.ts','utf8');
 const start=s.indexOf('const {data:closedPb'),end=s.indexOf('\n',s.indexOf('for(const x of closedPb',start));
 const code=s.slice(start,end);assert(code.includes('telegram_close_notified_at'));assert(!code.includes('.gt('));
 const sent=[],updates=[];const rows=[{id:1,net_pnl_usd:null,close_price:100},{id:2,net_pnl_usd:3,close_price:100,margin_usd:10,closed_at:'2020-01-01'},{id:3,net_pnl_usd:0,close_price:100,margin_usd:10},{id:4,net_pnl_usd:1,close_price:0}];
 const q={select(){return this},eq(){return this},not(){return this},is(){return this},order(){return Promise.resolve({data:rows})},update(v){updates.push(v);return this}};
 const ctx=vm.createContext({sb:{from:()=>q},Number,Date,send:async m=>sent.push(m),side:String,price:String,num:String});
 await vm.runInContext('(async()=>{'+code+'})()',ctx);assert.equal(sent.length,2);assert.equal(updates.length,2);
});
test('B recovery error stops new entries but not close management',()=>{const s=fs.readFileSync('supabase/functions/plan-b-executor/index.ts','utf8');assert(s.includes('recoveryErrors.length||exits?.ok===false?{mode:"reconciliation_required"'));assert(s.includes(':await closeDue({sb,bx})'));assert(s.includes('recovery_errors:recoveryErrors'));assert(s.includes('status:outcome.ok?200:503'));});
test('updated Edge entrypoints and dashboard scripts parse',()=>{
 for(const name of ['bingx-order-submit','bingx-account-read','coin-collector','plan-b-executor','plan-b-strategy','plan-b-account-read','telegram-trade-notify']){
  const s=fs.readFileSync('supabase/functions/'+name+'/index.ts','utf8');const js=stripTypeScriptTypes(s);new vm.SourceTextModule(js);
 }
 const html=fs.readFileSync('docs/index.html','utf8');for(const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))if(match[1].trim())new vm.Script(match[1]);new vm.Script(fs.readFileSync('docs/plan-controls.js','utf8'));
});

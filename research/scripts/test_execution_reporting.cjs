const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const {stripTypeScriptTypes}=require('node:module');
test('B late settlement delivery does not use a close-time watermark',async()=>{
 const s=fs.readFileSync('supabase/functions/telegram-trade-notify/index.ts','utf8');
 const start=s.indexOf('const {data:closedPb'),end=s.indexOf('\n',s.indexOf('for(const x of closedPb',start));
 const code=s.slice(start,end);assert(code.includes('telegram_close_notified_at'));assert(!code.includes('.gt('));
 const sent=[],updates=[];const rows=[{id:1,net_pnl_usd:null,close_price:100},{id:2,net_pnl_usd:3,close_price:100,margin_usd:10,closed_at:'2020-01-01'},{id:3,net_pnl_usd:0,close_price:100,margin_usd:10},{id:4,net_pnl_usd:1,close_price:0}];
 const q={select(){return this},eq(){return this},not(){return this},is(){return this},order(){return Promise.resolve({data:rows})},update(v){updates.push(v);return this}};
 const ctx=vm.createContext({sb:{from:()=>q},Number,Date,send:async m=>sent.push(m),side:String,price:String,num:String});
 await vm.runInContext('(async()=>{'+code+'})()',ctx);assert.equal(sent.length,2);assert.equal(updates.length,2);
});
test('B recovery error stops new entries but not close management',()=>{const s=fs.readFileSync('supabase/functions/plan-b-executor/index.ts','utf8');assert(s.includes('recoveryErrors.length?{mode:"reconciliation_required"'));assert(s.includes(':await closeDue({sb,bx})'));assert(s.includes('recovery_errors:recoveryErrors'));assert(s.includes('status:recoveryErrors.length?503:200'));});
test('updated Edge entrypoints and dashboard scripts parse',()=>{
 for(const name of ['bingx-order-submit','bingx-account-read','coin-collector','plan-b-executor','plan-b-strategy','plan-b-account-read','telegram-trade-notify']){
  const s=fs.readFileSync('supabase/functions/'+name+'/index.ts','utf8');const js=stripTypeScriptTypes(s);new vm.SourceTextModule(js);
 }
 const html=fs.readFileSync('docs/index.html','utf8');for(const match of html.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g))if(match[1].trim())new vm.Script(match[1]);new vm.Script(fs.readFileSync('docs/plan-controls.js','utf8'));
});

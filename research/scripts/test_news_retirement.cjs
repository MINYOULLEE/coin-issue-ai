const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const {stripTypeScriptTypes}=require('node:module');
const collector=fs.readFileSync('supabase/functions/coin-collector/index.ts','utf8');
test('collector keeps trading pipeline without any news request or stale news fields',async()=>{
  const box={Response,Date,console,Deno:{env:{get:()=>''},serve:fn=>box.handler=fn},fetch:()=>{throw Error('unexpected external request')}};
  vm.createContext(box);
  vm.runInContext(stripTypeScriptTypes(collector.replace(/^import .*;\r?\n/gm,'')),box);
  vm.runInContext(`schedulerAuthorized=async()=>true;current=async()=>({issues:[1],status:{blocked:{ok:false}},stats:{today:4},hot_themes:[1],hot_events:[1],keep:'untouched'});fetchMarket=async()=>({BTC:{price:10}});manageSignals=async(m,old)=>({active:[{id:7}],candidates:{preserved:old.keep},health:{ok:true}});save=async p=>saved=p;`,box);
  const response=await box.handler({method:'POST'});
  assert.equal(response.status,200);
  const result=await response.json();assert.equal(result.news_enabled,false);
  assert.equal(box.saved.keep,'untouched');assert.equal(box.saved.active_signals[0].id,7);
  assert.equal(box.saved.market.BTC.price,10);
  for(const key of ['issues','status','stats','hot_themes','hot_events'])assert.equal(key in box.saved,false,key);
  assert.doesNotMatch(collector,/fetchNews|SOURCES\.map|function feed\(/);
});
test('dashboard only exposes trading navigation and no news counters or render paths',()=>{
  const html=fs.readFileSync('docs/index.html','utf8');
  const filters=[...html.matchAll(/data-filter="([^"]+)"/g)].map(x=>x[1]);
  assert.deepEqual(filters,['plan-a','plan-b','plan-a-bingx','plan-a-history','plan-b-bingx','plan-b-history']);
  assert.doesNotMatch(html,/id="(?:today|urgent|good|bad)"|function render(?:Hot|Issues|Side)\(/);
  assert.match(html,/renderResearchA\(\)/);assert.match(html,/renderPlanB\('recommend'\)/);
});
test('retired-news receipt cleanup is scoped and never wipes trading alerts',()=>{
  const notify=fs.readFileSync('supabase/functions/telegram-trade-notify/index.ts','utf8');
  assert.match(notify,/news_enabled===false/);
  assert.match(notify,/key!=='__news_state'&&!key\.startsWith\('news:'\)/);
  assert.match(notify,/stableHealthAlerts\(priorHealth,problems\)/);
});

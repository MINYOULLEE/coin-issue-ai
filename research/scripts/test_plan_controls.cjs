const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const source=fs.readFileSync('docs/plan-controls.js','utf8');
const elements=new Map();
function el(id){if(!elements.has(id))elements.set(id,{textContent:'',innerHTML:'',dataset:{},remove(){},querySelector(){return {disabled:false}},insertAdjacentHTML(){}});return elements.get(id)}
const calls=[],storage=new Map();let fail=null;
const context=vm.createContext({console,Date,Number,Object,Promise,Error,FILTER:'trading',DATA:null,render(){},renderResearchA(){},renderPlanB(){},renderBingXHistoryData(){},document:{querySelector:el},$:el,esc:String,C:{supabaseUrl:'https://fixture.invalid'},bxHeaders:t=>({'x-dashboard-session':t}),sessionStorage:{getItem:k=>storage.get(k),setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},confirm:()=>true,fetch:async(url,options)=>{const body=JSON.parse(options.body);calls.push({url,body,token:options.headers['x-dashboard-session']});if(fail)return {ok:false,status:fail,json:async()=>({error:'fixture failure'})};return {ok:true,json:async()=>body.action==='trading_state'?{ok:true,state:{enabled:true,test_mode:false}}:body.action==='account'?{ok:true,account:{equity:150,available_margin:120},open_position_count:0,positions:[]}:{ok:true}}}});
vm.runInContext(source,context);
async function run(code){return vm.runInContext(code,context)}
(async()=>{
 storage.set('bingx_dashboard_session','token-A');storage.set('plan_b_dashboard_session','token-B');
 await run("pcRefresh('A')");await run("pcRefresh('B')");
 assert(calls.filter(c=>c.url.endsWith('bingx-account-read')).every(c=>c.token==='token-A'));
 assert(calls.filter(c=>c.url.endsWith('plan-b-account-read')).every(c=>c.token==='token-B'));
 assert.equal(el('pc-status-B').textContent,'실거래 · 신규 주문 허용');
 await run("pcToggle('B')");const toggle=calls.find(c=>c.body.action==='trading_toggle');assert.equal(toggle.body.enabled,false);assert(toggle.url.endsWith('plan-b-account-read'));assert.equal(toggle.token,'token-B');
 fail=503;await run("pcRefresh('B')");assert.match(el('pc-status-B').textContent,/미확인/);assert.equal(storage.get('plan_b_dashboard_session'),'token-B');assert.equal(await run('pcRuntime.B.state'),null);
 fail=401;await run("pcRefresh('B')");assert.equal(storage.has('plan_b_dashboard_session'),false);assert.equal(storage.get('bingx_dashboard_session'),'token-A');
 assert.equal(await run('pcMoney(null)'),'미확인');assert.equal(await run('pcMoney(0)'),'$0.00');
 console.log('PASS: separate endpoints/tokens, B-only toggle, 503 unknown, 401 isolated logout, missing vs zero');
})().catch(e=>{console.error(e);process.exitCode=1});

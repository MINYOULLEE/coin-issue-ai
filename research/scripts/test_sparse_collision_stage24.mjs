// Offline tests of current B functions; supplemental integration is NOT implemented here.
import test from 'node:test';
import assert from 'node:assert/strict';
import {eligible,executeBatch,closeDue} from '../../supabase/functions/_shared/plan_b_live_cycle.mjs';
const NOW=Date.parse('2026-08-31T00:01:00Z');
function fixture(status='closing'){
 const tables={plan_b_trading_state:[{id:'singleton',strategy_id:'b_reserved_margin_stage16',enabled:true,test_mode:false}],plan_b_execution_intents:[{signal_id:1,status,symbol:'AVAX',reserved_usd:90,close_attempt:1,close_client_order_id:'pb16-1-c1'}],plan_b_real_trades:[{id:1,signal_id:1,status:'open',symbol:'AVAX',side:'long',quantity:2,bingx_order_id:'entry',client_order_id:'pb16-1',plan_b_signals:{expires_at:new Date(NOW-1).toISOString()}}]};
 const sb={from(name){let filters=[],update=null;const q={select(){return q},eq(k,v){filters.push(r=>r[k]===v);return q},is(k,v){filters.push(r=>(r[k]??null)===v);return q},not(k,op,v){filters.push(r=>op==='is'?r[k]!=null:!v.slice(1,-1).split(',').includes(r[k]));return q},single(){return {...q,then(resolve){const a=tables[name].filter(r=>filters.every(f=>f(r)));resolve({data:a[0],error:null});}}},update(v){update=v;return q},then(resolve){const a=tables[name].filter(r=>filters.every(f=>f(r)));if(update)a.forEach(r=>Object.assign(r,update));resolve({data:a,error:null});}};return q;},rpc(){throw Error('must not reserve');}};
 let submits=0;let residual=1;
 const bx={read:async path=>path.includes('positions')?[{symbol:'AVAX-USDT',positionSide:'LONG',positionAmt:residual}]:[],lookup:async()=>({terminal:false,status:'partially_filled'}),submit:async()=>{submits++;return {status:'unknown'};}};
 return {sb,bx,now:()=>NOW,tables,get submits(){return submits},setResidual:v=>residual=v};
}
test('closing, partial and unknown reservations block a new B batch without exchange writes',async()=>{
 for(const status of ['closing','partial','unknown','submitted']){const f=fixture(status);f.bx.read=async()=>{throw Error('must stop before exchange');};const r=await executeBatch(f);assert.equal(r.mode,'reconciliation_required');assert.equal(f.submits,0);assert.equal(f.tables.plan_b_execution_intents[0].reserved_usd,90);}
});
test('partial close remains open and does not duplicate a pending close',async()=>{const f=fixture();await closeDue(f);await closeDue(f);assert.equal(f.submits,0);assert.equal(f.tables.plan_b_real_trades[0].status,'open');assert.equal(f.tables.plan_b_execution_intents[0].reserved_usd,90);});
test('terminal partial close retries residual only; unfilled residual still stays open',async()=>{const f=fixture();f.bx.lookup=async o=>o.clientOrderId==='pb16-1-c1'?{terminal:true,status:'filled'}:{status:'not_found'};let qty;f.bx.submit=async o=>{qty=o.quantity;return {status:'unknown'};};await closeDue(f);assert.equal(qty,1);assert.equal(f.tables.plan_b_real_trades[0].status,'open');assert.equal(f.tables.plan_b_execution_intents[0].status,'closing');});
test('current B entry TTL refuses 5/10-minute stale entries',()=>{for(const minutes of [5,10])assert.equal(eligible({symbol:'AVAX',strategy_id:'b_reserved_margin_stage16',side:'long',leverage:3,hold_hours:13,confirmed_at:new Date(NOW-minutes*60000).toISOString(),entry_deadline:new Date(NOW+60000).toISOString()},NOW),false);});
test('new ALGO ETH VET rules are NOT silently enabled in current B',()=>{for(const symbol of ['ALGO','ETH','VET'])assert.equal(eligible({symbol,strategy_id:'b_reserved_margin_stage16',side:'long',leverage:3,hold_hours:1,confirmed_at:new Date(NOW).toISOString(),entry_deadline:new Date(NOW+60000).toISOString()},NOW),false);});

import test from 'node:test';
import assert from 'node:assert/strict';
import {createAEntryCycle} from '../../supabase/functions/_shared/a_entry_cycle.mjs';
const p={signal:{id:101,symbol:'BTC',side:'long',signal_type:'answer_mdd30'},symbol:'BTC-USDT',side:'BUY',positionSide:'LONG',leverage:10,quantity:2,signal_price:100,equity:1000,executor_version:62,max_concurrent_positions:5,max_same_direction:5};
function fixture(order={orderId:'1234567890123456789',executedQty:2,avgPrice:101,status:'FILLED'},options={}){
 const calls=[],writes=[];let reservation=null,trade=options.closed?{id:9,status:'closed'}:null;
 const db=async(path,init={})=>{const method=init.method||'GET',body=init.body&&JSON.parse(init.body);writes.push({path,method,body});
  if(path.startsWith('rpc/')){if(reservation||trade)return {reserved:false};reservation={signal_id:101};return {reserved:true};}
  if(path.startsWith('real_trading_state'))return [{enabled:!options.off,test_mode:false}];
  if(path.startsWith('trade_execution_reservations')){if(method==='PATCH')Object.assign(reservation||{},body);if(method==='DELETE')reservation=null;if(method==='GET')return reservation?.request_payload?[reservation]:[];return null;}
  if(path.startsWith('real_trades')){if(method==='GET')return trade?[trade]:[];if(options.dbFail)throw Error('ledger unavailable');trade={id:9,...body};}
  return null;
 };
 const signed=async(method,path,args)=>{calls.push({method,path,args});if(path.endsWith('/leverage'))return {};if(options.timeout&&method==='POST')throw Error('timeout');return order;};
 return {cycle:createAEntryCycle({db,signed}),calls,writes,get reservation(){return reservation},get trade(){return trade}};
}
test('A records actual execution, not requested price',async()=>{const f=fixture();const r=await f.cycle.submit(p);assert.equal(r.fill_price,101);assert.equal(f.trade.entry_price,101);assert.equal(f.reservation,null);});
test('A zero execution never creates a position',async()=>{const f=fixture({orderId:'123',executedQty:0,avgPrice:0,status:'NEW'});assert.equal((await f.cycle.submit(p)).pending,true);assert.equal(f.trade,null);assert(f.reservation.request_payload);});
test('A timeout retains durable intent; recovery only queries and settles',async()=>{const f=fixture(undefined,{timeout:true});assert.equal((await f.cycle.submit(p)).pending,true);assert.equal(f.reservation.execution_status,'unknown');const n=f.calls.length;assert.equal((await f.cycle.recover()).ok,true);assert(f.calls.slice(n).every(c=>c.method==='GET'));assert.equal(f.trade.quantity,2);assert.equal(f.reservation,null);});
test('A ledger failure after acceptance retains reservation',async()=>{const f=fixture(undefined,{dbFail:true});assert.equal((await f.cycle.submit(p)).pending,true);assert(f.reservation);assert(!f.writes.some(c=>c.method==='DELETE'));});
test('A partial fill uses actual quantity and keeps reservation',async()=>{const f=fixture({orderId:'123',executedQty:.5,avgPrice:102,status:'PARTIALLY_FILLED'});assert.equal((await f.cycle.submit(p)).pending,true);assert.equal(f.trade.quantity,.5);assert.equal(f.reservation.execution_status,'partial');});
test('A definitive zero-fill rejection releases slot without ledger',async()=>{const f=fixture({orderId:'123',executedQty:0,avgPrice:0,status:'REJECTED'});assert.equal((await f.cycle.submit(p)).rejected,true);assert.equal(f.trade,null);assert.equal(f.reservation,null);});
test('A disabled state sends no exchange requests',async()=>{const f=fixture(undefined,{off:true});await assert.rejects(f.cycle.submit(p),/disabled/);assert.equal(f.calls.length,0);});
test('A duplicate intent cannot resubmit',async()=>{const f=fixture(undefined,{timeout:true});await f.cycle.submit(p);await f.cycle.submit(p);assert.equal(f.calls.filter(c=>c.method==='POST'&&c.path.endsWith('/order')).length,1);});
test('A recovery cannot reopen an already closed ledger',async()=>{const f=fixture(undefined,{closed:true});await f.cycle.settle(p,{orderId:'123',executedQty:2,avgPrice:101,status:'FILLED'});assert.equal(f.trade.status,'closed');});
test('B payload is rejected by A',async()=>{const f=fixture();await assert.rejects(f.cycle.submit({...p,signal:{...p.signal,signal_type:'b_reserved_margin_stage16'}}),/invalid A/);assert.equal(f.calls.length,0);});

import test from 'node:test';
import assert from 'node:assert/strict';
import {closeManagedTrade,managedCloseSettlement} from '../../supabase/functions/_shared/managed_close.mjs';
function fixture(){
 const trade={id:42,status:'open',quantity:2,close_context:null};
 const f={trade,actual:2,order:{status:'NEW',executedQty:0},sent:[],closed:0,
  position:async()=>f.actual,lookup:async()=>f.order,cancelStop:async()=>{},
  submit:async(id,quantity)=>{f.sent.push({id,quantity})},
  claim:async(previous,next)=>{if(JSON.stringify(trade.close_context)!==JSON.stringify(previous))return false;trade.status='closing';trade.close_context=next;return true},
  save:async()=>{},finish:async()=>{trade.status='closed';f.closed++}};return f;
}
test('accepted zero-fill close remains closing, and reload only looks up existing order',async()=>{
 const f=fixture();await assert.rejects(closeManagedTrade(f),/pending/);assert.equal(f.closed,0);
 await assert.rejects(closeManagedTrade(f),/pending/);assert.equal(f.sent.length,1);
 f.order={status:'FILLED',executedQty:2};f.actual=0;await closeManagedTrade(f);assert.equal(f.closed,1);assert.equal(f.sent.length,1);
});
test('submit timeout preserves durable identity and never blindly resubmits',async()=>{
 const f=fixture();f.submit=async()=>{throw Error('timeout')};await assert.rejects(closeManagedTrade(f),/timeout/);
 assert.equal(f.trade.status,'closing');let sent=0;f.submit=async()=>{sent++};f.lookup=async()=>{throw Error('not found')};
 await assert.rejects(closeManagedTrade(f),/not found/);assert.equal(sent,0);
});
test('terminal partial fill retries only owned remainder and preserves manual quantity',async()=>{
 const f=fixture();f.actual=5;await assert.rejects(closeManagedTrade(f));
 f.actual=4;f.order={status:'CANCELED',executedQty:1};
 f.submit=async(id,quantity)=>{f.sent.push({id,quantity});f.actual=3;f.order={status:'FILLED',executedQty:quantity}};
 await closeManagedTrade(f);assert.deepEqual(f.sent.map(x=>x.quantity),[2,1]);assert.equal(f.closed,1);assert.equal(f.actual,3);
});
test('filled order without verified position reduction cannot close ledger',async()=>{
 const f=fixture();f.order={status:'FILLED',executedQty:2};await assert.rejects(closeManagedTrade(f),/pending/);assert.equal(f.closed,0);
 await assert.rejects(closeManagedTrade(f),/disagree/);assert.equal(f.sent.length,1);
});
test('failed protective cancellation leaves an unsubmitted close retryable',async()=>{
 const f=fixture();f.cancelStop=async()=>{throw Error('cancel unavailable')};await assert.rejects(closeManagedTrade(f),/cancel/);
 assert.equal(f.trade.status,'open');assert.equal(f.trade.close_context,null);assert.equal(f.sent.length,0);
});
test('managed settlement requires unique matching actual net history and excludes manual overlap',()=>{
 const opened=Date.parse('2026-09-15T01:00:00Z'),trade={symbol:'BTC',side:'long',quantity:2,opened_at:new Date(opened).toISOString()};
 const row={symbol:'BTC-USDT',positionSide:'LONG',quantity:2,openTime:opened,closeTime:opened+60000,avgClosePrice:100,netProfit:12};
 assert.equal(managedCloseSettlement([row],trade).net,12);
 assert.equal(managedCloseSettlement([{...row,netProfit:undefined}],trade),null);
 assert.equal(managedCloseSettlement([row,row],trade),null);
 assert.equal(managedCloseSettlement([row],{...trade,close_context:{manualRemainder:1}}),null);
});
test('invalid position response cannot be treated as zero',async()=>{
 const f=fixture();f.actual=NaN;await assert.rejects(closeManagedTrade(f),/invalid exchange/);assert.equal(f.closed,0);assert.equal(f.sent.length,0);
});
test('failed atomic claim sends no close',async()=>{
 const f=fixture();f.claim=async()=>false;await assert.rejects(closeManagedTrade(f),/claimed/);assert.equal(f.sent.length,0);
});

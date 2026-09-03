import test from 'node:test';
import assert from 'node:assert/strict';
import {decidePlanB,signalRow} from '../../supabase/functions/_shared/plan_b_signals.mjs';
import {validatePlanBEntry,priceStillExecutable} from '../../supabase/functions/_shared/plan_b_execution_guard.ts';
const H=3600000;
function candles(){return Array.from({length:200},(_,i)=>({t:i*H,o:100+i,h:102+i,l:99+i,c:101+i,v:100}));}
test('completed candles only and exact Stage16 metadata',()=>{
  const x=candles(),d=decidePlanB('AVAX',x,200*H),r=signalRow('AVAX',d,200*H);
  assert.equal(d.side,'short');assert.equal(r.hold_hours,13);assert.equal(r.strategy_params.research_hold_index,12);
  const forming={t:200*H,o:1,h:9999,l:1,c:1,v:1};
  assert.deepEqual(decidePlanB('AVAX',[...x,forming],200*H),d);
});
test('stale, gapped, invalid candles and A symbols fail closed',()=>{
  const x=candles();assert.equal(decidePlanB('AVAX',x,200*H+300000).side,null);
  assert.throws(()=>decidePlanB('BTC',x,200*H));x[100].t+=H;assert.throws(()=>decidePlanB('AVAX',x,200*H));
});
test('RSI excludes signal candle return',()=>{
  const x=candles();x.at(-1).c=1;x.at(-1).l=1;
  assert.equal(decidePlanB('AVAX',x,200*H).meta.rsi,100);
});
test('expiry/future clock, A symbol and nonfinite price rejected',()=>{
  const s={plan:'B',symbol:'AVAX',side:'long',id:12,signalPrice:100,confirmedAt:new Date(200*H).toISOString()};
  assert.equal(validatePlanBEntry(s,200*H).clientOrderId,'pb35-12');
  assert.equal(validatePlanBEntry(s,200*H-1).ok,false);assert.equal(validatePlanBEntry(s,200*H+300000).ok,false);
  assert.equal(validatePlanBEntry({...s,symbol:'BTC'},200*H).ok,false);
  assert.equal(priceStillExecutable(s,Infinity),false);assert.equal(priceStillExecutable(s,100.36),false);
});

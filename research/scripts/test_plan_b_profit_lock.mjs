import test from 'node:test';
import assert from 'node:assert/strict';
import {advanceProfitLock,atr24,normalizeHourlyKlines,profitFloorBreached,profitLockPolicy} from '../../supabase/functions/_shared/plan_b_profit_lock.mjs';

test('ATR24 uses only completed prior candles',()=>{
 const start=Date.parse('2026-09-01T00:00:00Z');
 const rows=Array.from({length:25},(_,i)=>({t:start+i*3600000,o:100,h:102,l:99,c:101}));
 assert.equal(atr24(rows),3);
 assert.equal(normalizeHourlyKlines([...rows,{t:start+25*3600000,o:101,h:500,l:1,c:200}],start+25*3600000).length,25);
});

test('only the three approved symbols receive a frozen entry policy',()=>{
 assert.equal(profitLockPolicy({symbol:'AVAX',side:'long',entryPrice:100,atr:2}),null);
 const policy=profitLockPolicy({symbol:'ICP',side:'long',entryPrice:100,atr:2});
 assert.equal(policy.policy,'causal_atr_peak_close_stage66_v1');
 assert(Math.abs(policy.triggerPct-0.01494823908876756)<1e-15);
 assert.equal(policy.keepFraction,.7);
});

test('completed close arms a monotonic long floor and a later mark breaches it',()=>{
 const base={side:'long',entry_price:100,profit_lock_policy:'causal_atr_peak_close_stage66_v1',profit_lock_trigger_pct:.02,profit_lock_keep_fraction:.7};
 const first=advanceProfitLock(base,{t:Date.parse('2026-09-07T00:00:00Z'),c:103});
 assert.equal(first.profit_lock_floor_price,102.1);
 const second=advanceProfitLock({...base,...first},{t:Date.parse('2026-09-07T01:00:00Z'),c:102.5});
 assert.equal(second.profit_lock_floor_price,102.1);
 assert.equal(profitFloorBreached({...base,...second},102,Date.parse('2026-09-07T02:01:00Z')),true);
 assert.equal(profitFloorBreached({...base,...second},102.2,Date.parse('2026-09-07T02:01:00Z')),false);
});

test('short protection mirrors long and cannot fire before activation',()=>{
 const base={side:'short',entry_price:100,profit_lock_policy:'causal_atr_peak_close_stage66_v1',profit_lock_trigger_pct:.02,profit_lock_keep_fraction:.75};
 const idle=advanceProfitLock(base,{t:Date.parse('2026-09-07T00:00:00Z'),c:99});
 assert.equal(idle.profit_lock_floor_price,null);
 assert.equal(profitFloorBreached({...base,...idle},200,Date.parse('2026-09-07T01:01:00Z')),false);
 const armed=advanceProfitLock({...base,...idle},{t:Date.parse('2026-09-07T01:00:00Z'),c:96});
 assert.equal(armed.profit_lock_floor_price,97);
 assert.equal(profitFloorBreached({...base,...armed},97.1,Date.parse('2026-09-07T02:01:00Z')),true);
});
test('a completed minute wick crossing the floor is not missed when mark recovers',()=>{const trade={side:'long',profit_lock_floor_price:102,profit_lock_armed_at:'2026-09-07T02:00:00Z'};assert.equal(profitFloorBreached(trade,103,Date.parse('2026-09-07T02:02:00Z'),[{t:Date.parse('2026-09-07T02:01:00Z'),h:103,l:101.9}]),true);});

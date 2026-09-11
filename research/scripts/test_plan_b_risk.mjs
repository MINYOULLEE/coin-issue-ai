import test from 'node:test';import assert from 'node:assert/strict';
import {btcRegime,applyBtcEntryGuard} from '../../supabase/functions/_shared/plan_b_risk.mjs';
const H=3600000,boundary=100*H;
const candles=(latest=94)=>Array.from({length:100},(_,i)=>({t:i*H,c:i===99?latest:100}));
test('BTC guard uses exactly the two completed closes 72h apart',()=>{
 const r=btcRegime(candles(94),boundary,72,-.06);assert.equal(r.available,true);assert.equal(r.blocked,true);assert.equal(r.latestCloseAt,boundary);
});
test('missing BTC history blocks protected entries only',()=>{
 const decisions={BCH:{side:'long',diagnostic:{}},ADA:{side:'long',diagnostic:{}}};
 const guarded=applyBtcEntryGuard(decisions,btcRegime([],boundary),['BCH']);
 assert.equal(guarded.BCH.side,null);assert.equal(guarded.ADA.side,'long');assert.equal(guarded.BCH.diagnostic.btc_regime.entry_blocked,true);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { allocatePlanB, PLAN_B_STANDARD as S } from '../../supabase/functions/_shared/plan_b_sizing.mjs';
const args = {plan:'B',strategyId:S.strategy_id,balance:100,equity:100,reservedMargin:0,proposals:[{symbol:'ICP',entryPrice:10}]};
test('single 115% target is clipped with fees reserved',()=>{
  const r=allocatePlanB(args),p=r.orders[0];
  assert.equal(r.available,95);assert(p.margin<95);assert(p.requiredReservation<=95+1e-10);
  assert.equal(p.quantity,p.margin*5/10);
});
test('simultaneous signals share only free collateral',()=>{
  const r=allocatePlanB({...args,reservedMargin:60,proposals:[{symbol:'ICP',entryPrice:10},{symbol:'AVAX',entryPrice:30}]});
  assert.equal(r.available,35);assert(r.orders.reduce((a,p)=>a+p.requiredReservation,0)<=35+1e-10);
  assert.equal(r.orders[0].margin,r.orders[1].margin);
});
test('insufficient margin rejects, no leverage fallback',()=>{
  const r=allocatePlanB({...args,balance:80,equity:70,reservedMargin:75});
  assert(r.orders[0].rejected);assert.equal(r.orders[0].quantity,0);
});
test('A strategy, wrong version and duplicate proposals fail closed',()=>{
  assert.throws(()=>allocatePlanB({...args,plan:'A'}));
  assert.throws(()=>allocatePlanB({...args,strategyId:'answer_mdd30'}));
  assert.throws(()=>allocatePlanB({...args,proposals:[...args.proposals,...args.proposals]}));
  assert.throws(()=>allocatePlanB({...args,proposals:[{symbol:'BTC',entryPrice:1}]}));
});
test('150 dollars scales quantities but not percentage allocation',()=>{
  const a=allocatePlanB(args),b=allocatePlanB({...args,balance:150,equity:150});
  assert(Math.abs(b.orders[0].quantity/a.orders[0].quantity-1.5)<1e-12);
});

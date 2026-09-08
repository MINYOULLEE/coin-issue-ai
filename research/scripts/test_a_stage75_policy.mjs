import test from 'node:test';
import assert from 'node:assert/strict';
import {A_STAGE75,nextDrawdownGuard,stage75Target,stage75StopPrice,rebalanceDelta,transitionCapacity} from '../../supabase/functions/_shared/a_stage75_policy.mjs';

test('guard activates at 35 percent and recovers only at 17.5 percent',()=>{
 assert.equal(nextDrawdownGuard({equity:65,peak:100}).active,true);
 assert.equal(nextDrawdownGuard({equity:80,peak:100,active:true}).active,true);
 assert.equal(nextDrawdownGuard({equity:82.5,peak:100,active:true}).active,false);
});
test('normal and guarded exposure preserve signed base target',()=>{
 assert.equal(stage75Target({baseExposure:.4,equity:100,price:10,guardActive:false}).signedQuantity,5.6);
 assert.ok(Math.abs(stage75Target({baseExposure:-.4,equity:100,price:10,guardActive:true}).signedQuantity+4.2)<1e-12);
});
test('stop is exactly 15 percent from actual fill',()=>{
 assert.equal(stage75StopPrice({fillPrice:100,side:'long'}),85);
 assert.ok(Math.abs(stage75StopPrice({fillPrice:100,side:'short'})-115)<1e-12);
});
test('rebalance sends only rounded delta and skips unsendable dust',()=>{
 assert.deepEqual(rebalanceDelta({actualSignedQuantity:1,targetSignedQuantity:1.009,step:.01,minQuantity:.01,minNotional:2,price:100}),{action:'hold',quantity:0,reason:'below_minimum_delta'});
 assert.equal(rebalanceDelta({actualSignedQuantity:1,targetSignedQuantity:.5,step:.01,minQuantity:.01,minNotional:2,price:100}).action,'sell');
});
test('2.24x gross at 3x uses 74.67 percent initial margin',()=>{
 const x=transitionCapacity({equity:100,currentGross:160,targetGross:224});
 assert.ok(Math.abs(x.targetMarginRatio-.7466666666666667)<1e-12);assert.equal(x.withinEntryCap,true);
});
test('policy constants match adopted Stage75',()=>{
 assert.equal(A_STAGE75.leverage,3);assert.equal(A_STAGE75.normalScale,1.4);assert.equal(A_STAGE75.maxGross,2.24);
});

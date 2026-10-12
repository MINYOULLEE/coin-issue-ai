import test from 'node:test';import assert from 'node:assert/strict';
import {closedOrderGroupVerified,isReduceOrder} from '../../supabase/functions/_shared/closed_order_lifecycle.mjs';
const row=(time,reduceOnly,qty=10)=>({time,reduceOnly,executedQty:qty,positionId:'p'});
test('complete chronological lifecycle is a closed trade',()=>assert(closedOrderGroupVerified([row(1700000000000,false),row(1700000060000,true)])));
test('observed TRX backwards window cannot manufacture a loss',()=>assert.equal(closedOrderGroupVerified([row(1700000060000,false),row(1700000000000,true)]),false));
test('a still live position cannot be counted as a completed loss',()=>assert.equal(closedOrderGroupVerified([row(1700000000000,false),row(1700000060000,true)],new Set(['p'])),false));
test('excess closes from a truncated query fail instead of inferring full closure',()=>assert.equal(closedOrderGroupVerified([row(1700000000000,false,5),row(1700000060000,true,10)]),false));
test('partial closes and missing time/quantity never become full closure',()=>{assert.equal(closedOrderGroupVerified([row(1700000000000,false),row(1700000060000,true,5)]),false);assert.equal(closedOrderGroupVerified([{reduceOnly:false,executedQty:10,positionId:'p'},row(1700000060000,true)]),false);});
test('string false is an opening order, not a reducing order',()=>{assert.equal(isReduceOrder({reduceOnly:'false'}),false);assert.equal(isReduceOrder({reduceOnly:'true'}),true);});

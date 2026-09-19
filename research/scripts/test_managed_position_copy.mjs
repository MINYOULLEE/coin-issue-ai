import test from 'node:test';
import assert from 'node:assert/strict';
import {copyDelta,normalizedPositions,positionKey,targetQuantity} from '../../supabase/functions/_shared/managed_position_copy.mjs';

test('copy target preserves owner exposure as an equity ratio',()=>{
 assert.equal(targetQuantity(2,1000,100,3),.2);
 assert.equal(targetQuantity(.0256,2171.4843,98.9136,4),.0011);
});

test('copy delta ignores exchange dust and labels reductions',()=>{
 assert.equal(copyDelta(1,1.001,3,.01,2,100),null);
 assert.deepEqual(copyDelta(2,1.5,3,.01,2,100),{quantity:.5,reduce:true});
});

test('exchange positions normalize without mixing hedge sides',()=>{
 const rows=normalizedPositions([{symbol:'ETH-USDT',positionSide:'LONG',positionAmt:'1.2',avgPrice:'2000',markPrice:'2010',leverage:'5'}]);
 assert.equal(positionKey(rows[0].symbol,rows[0].side),'ETH-USDT:LONG');
 assert.equal(rows[0].quantity,1.2);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {hasAnyOppositePosition,manualOppositeQuantity} from '../../supabase/functions/_shared/a_manual_conflict_guard.mjs';

const positions=[
 {symbol:'ETH-USDT',positionSide:'LONG',positionAmt:1.05},
 {symbol:'ETH-USDT',positionSide:'SHORT',positionAmt:.52},
];

test('manual long blocks a new automatic short',()=>{
 assert.equal(hasAnyOppositePosition(positions,'ETH','short'),true);
});

test('manual short blocks a new automatic long',()=>{
 assert.equal(hasAnyOppositePosition(positions,'ETH','long'),true);
});

test('guard subtracts automatic opposite ledger before identifying manual quantity',()=>{
 assert.equal(manualOppositeQuantity(positions,[{symbol:'ETH',side:'short',quantity:.52}],'ETH','long'),0);
 assert.equal(manualOppositeQuantity(positions,[{symbol:'ETH',side:'short',quantity:.20}],'ETH','long'),.32);
});

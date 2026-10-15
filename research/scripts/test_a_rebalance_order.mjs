import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {aRebalanceOrder,aAdjustmentPending} from '../../supabase/functions/_shared/a_rebalance_order.mjs';
test('observed XRP/TRX/SOL ordering adjusts existing positions before entry',()=>{
 assert.deepEqual(aRebalanceOrder(['BTC','ETH','XRP','TRX','SOL'],[{symbol:'TRX'},{symbol:'SOL'}],[]),['TRX','SOL','BTC','ETH','XRP']);
});
test('legacy holdings first; stable order, no duplicates, inputs unchanged',()=>{
 const assets=['BTC','ETH','XRP','TRX','SOL'];
 assert.deepEqual(aRebalanceOrder(assets,[{symbol:'SOL'}],[{symbol:'ETH'},{symbol:'SOL'}]),['ETH','SOL','BTC','XRP','TRX']);
 assert.deepEqual(assets,['BTC','ETH','XRP','TRX','SOL']);
 assert.deepEqual(aRebalanceOrder(assets,[],[]),assets);
});
test('unconfirmed adjustments block later new entries; held/manual-held do not',()=>{
 for(const status of ['close_failed','resize_failed','entry_failed','entry_pending'])assert.equal(aAdjustmentPending([{status}]),true);
 assert.equal(aAdjustmentPending(['held','resized','cash','manual_held','entered'].map(status=>({status}))),false);
});
test('collector uses execution ordering and guard without altering strategy asset set',()=>{
 const s=readFileSync('supabase/functions/coin-collector/index.ts','utf8');
 assert.ok(s.includes('for(const symbol of aRebalanceOrder(ANSWER_ASSETS,open(),legacyActive))'));
 assert.ok(s.indexOf('aAdjustmentPending(audit)')<s.indexOf('const entered=answer?.side'));
 assert.ok(s.includes('const ANSWER_ASSETS = ["BTC","ETH","XRP","TRX","SOL"]'));
 const e=readFileSync('supabase/functions/bingx-order-execute/index.ts','utf8');
 assert.ok(e.includes('entry_sizing_diagnostic:{equity,available_margin:availableMargin'));
});

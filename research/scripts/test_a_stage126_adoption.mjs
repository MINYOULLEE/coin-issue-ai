import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const standard=JSON.parse(fs.readFileSync('strategy/mdd30_standard.json','utf8'));
const collector=fs.readFileSync('supabase/functions/coin-collector/index.ts','utf8');
const executor=fs.readFileSync('supabase/functions/bingx-order-execute/index.ts','utf8');

test('A standard freezes Stage126 guard and selective resize',()=>{
 assert.equal(standard.standard_version,'mdd30_selective_resize_stage126_v1');
 assert.equal(standard.sol_short_regime_guard.btc_completed_168h_return_min_pct,3.5);
 assert.equal(standard.sol_short_regime_guard.sol_completed_168h_return_min_pct,12);
 assert.equal(standard.selective_resize.threshold_pct_of_current_actual_equity,1.25);
 assert.deepEqual(standard.selective_resize.hold_existing_quantity_when_below_threshold.map(x=>`${x.symbol}:${x.side}:${x.resize}`),['SOL:long:decrease','BTC:short:decrease']);
});
test('collector preserves same-side positions and applies only the adopted SOL short guard',()=>{
 assert.match(collector,/const solShortBlocked=.*\.035.*\.12.*answerBreadth>=3/);
 assert.match(collector,/symbol==="SOL"&&answer\?\.side==="short"&&solShortBlocked/);
 assert.doesNotMatch(collector,/current\.side!==answer\.side\|\|Math\.abs\(Number\(current\.entry_metrics/);
});
test('executor calls the shared selective hold before exchange resize order',()=>{
 const hold=executor.indexOf('if (selective.hold)');
 const resizeOrder=executor.indexOf('const adding = targetQty > currentQty');
 assert.ok(hold>0&&resizeOrder>hold);
 assert.match(executor,/selectiveResizeHold/);
});

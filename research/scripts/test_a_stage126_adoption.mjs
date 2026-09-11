import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';

const standard=JSON.parse(fs.readFileSync('strategy/mdd30_standard.json','utf8'));
const collector=fs.readFileSync('supabase/functions/coin-collector/index.ts','utf8');
const executor=fs.readFileSync('supabase/functions/bingx-order-execute/index.ts','utf8');
const notifier=fs.readFileSync('supabase/functions/telegram-trade-notify/index.ts','utf8');

test('A standard freezes Stage135 rally guard and Stage126 selective resize',()=>{
 assert.equal(standard.standard_version,'mdd30_intraday_rally_guard_stage135_v1');
 assert.equal(standard.sol_short_regime_guard.btc_completed_168h_return_min_pct,3.5);
 assert.equal(standard.sol_short_regime_guard.sol_completed_168h_return_min_pct,12);
 assert.equal(standard.selective_resize.threshold_pct_of_current_actual_equity,1.25);
 assert.deepEqual(standard.selective_resize.hold_existing_quantity_when_below_threshold.map(x=>`${x.symbol}:${x.side}:${x.resize}`),['SOL:long:decrease','BTC:short:decrease']);
 assert.deepEqual(standard.intraday_rally_guard.symbols_reduced,['ETH','XRP','SOL']);
 assert.equal(standard.intraday_rally_guard.confirmation_hours,2);
 assert.equal(standard.intraday_rally_guard.phase_1.remaining_quantity_fraction,.05);
 assert.equal(standard.intraday_rally_guard.phase_2.remaining_quantity_fraction,0);
});
test('collector and executor contain isolated Stage135 rally guard path',()=>{
 assert.match(collector,/action:"rally_guard_mdd30"/);
 assert.match(collector,/\["ETH","XRP","SOL"\]/);
 assert.match(executor,/handleMdd30RallyGuard/);
 assert.match(executor,/A rally guard only supports ETH\/XRP\/SOL shorts/);
 assert.match(collector,/last_evaluated_closed_at=commonClosedAt-1/);
 assert.match(collector,/daily_a_anchor_price/);
 assert.match(executor,/rally_guard_notification_pending:true/);
 assert.match(notifier,/장중 급등 방어 부분청산/);
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

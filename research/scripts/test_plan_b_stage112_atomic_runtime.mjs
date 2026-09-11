import assert from 'node:assert/strict';
import fs from 'node:fs';

const path = new URL('../../supabase/migrations/20260910121000_fix_plan_b_stage112_atomic_runtime.sql', import.meta.url);
const sql = fs.readFileSync(path, 'utf8');

for (const required of [
  'plan_b_publish_opportunities',
  'plan_b_reserve_intents',
  'plan_b_claim_intent',
  'b_regime_guard_stage112_v1',
  'b_regime_guard_stage112',
  'pb112:',
  'pb112-',
  "16|26|35|45|66|93|112",
]) assert.ok(sql.includes(required), `missing Stage112 atomic runtime repair: ${required}`);

assert.match(sql, /if definition not like[\s\S]*raise exception 'unexpected plan_b_publish_opportunities source'/);
assert.match(sql, /if definition not like[\s\S]*raise exception 'unexpected plan_b_reserve_intents source'/);
assert.match(sql, /if definition not like[\s\S]*raise exception 'unexpected plan_b_claim_intent source'/);

console.log('Plan B Stage112 atomic runtime migration regression: PASS');

import test from 'node:test';
import assert from 'node:assert/strict';
import {normalizeProbabilities,seedDecision,scoreOutcome} from '../../supabase/functions/_shared/rlcd_shadow.mjs';

test('R-Lab probabilities always sum to one',()=>{
  const p=normalizeProbabilities({long:7,short:2,no_trade:1});
  assert(Math.abs(p.long+p.short+p.no_trade-1)<1e-12);
});

test('R-Lab seed layer remains no-trade when directional edge is weak',()=>{
  const d=seedDecision({micro:{long:40,short:30,range:30}});
  assert.equal(d.action,'no_trade');
});

test('R-Lab scores all three counterfactual actions after costs',()=>{
  const r=scoreOutcome({action:'long',entry:100,exit:102,high:103,low:99,horizonHours:4});
  assert(r.net_return_pct<2&&r.net_return_pct>1.7);
  assert(r.counterfactual.short_net_pct<0);
  assert.equal(r.successful,true);
});

test('R-Lab shared module has no execution or exchange credential path',async()=>{
  const source=await import('node:fs/promises').then(fs=>fs.readFile('supabase/functions/_shared/rlcd_shadow.mjs','utf8'));
  assert(!/order|api.?key|secret.?key|real_trades|plan_b_real_trades/i.test(source));
});

test('R-Lab edge function excludes the display-only USDT market row',async()=>{
  const source=await import('node:fs/promises').then(fs=>fs.readFile('supabase/functions/rlcd-shadow/index.ts','utf8'));
  assert.match(source,/NON_TRADING_MARKET_KEYS=new Set\(\['USDT'\]\)/);
  assert.match(source,/NON_TRADING_MARKET_KEYS\.has\(symbol\)/);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import {marginReturnPct, withMarginReturn} from '../../supabase/functions/_shared/trade_returns.mjs';

test('closed B trade margin return uses net PnL divided by actual margin', () => {
  assert.equal(marginReturnPct({status:'closed', margin_usd:554.56, net_pnl_usd:5.13}), 5.13 / 554.56 * 100);
  assert.equal(marginReturnPct({status:'closed', margin_usd:620.59, net_pnl_usd:-71.39}), -71.39 / 620.59 * 100);
});

test('missing, invalid, zero-margin and open trades never show a guessed return', () => {
  assert.equal(marginReturnPct({status:'open', margin_usd:100, net_pnl_usd:5}), null);
  assert.equal(marginReturnPct({status:'closed', margin_usd:0, net_pnl_usd:5}), null);
  assert.equal(marginReturnPct({status:'closed', margin_usd:null, net_pnl_usd:5}), null);
  assert.equal(marginReturnPct({status:'closed', margin_usd:100, net_pnl_usd:null}), null);
});

test('API row keeps source fields and adds margin_return_pct', () => {
  const row={symbol:'UNI',status:'closed',margin_usd:610.46,net_pnl_usd:14.15};
  assert.deepEqual(withMarginReturn(row), {...row,margin_return_pct:14.15/610.46*100});
});

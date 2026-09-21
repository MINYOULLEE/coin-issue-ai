const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs');
const source=fs.readFileSync('supabase/functions/weekly-snapshot/index.ts','utf8');

test('weekly snapshot reads the canonical realized-basis balance for both plans',()=>{
  assert.match(source,/const value=j\.stats\?\.current_balance_usd/);
  assert.doesNotMatch(source,/realized_equity_usd/);
});

test('weekly snapshot keeps A and B account readers isolated',()=>{
  assert.match(source,/plan==="A"\?"bingx-account-read":"plan-b-account-read"/);
  assert.match(source,/for\(const plan of \["A","B"\]/);
});

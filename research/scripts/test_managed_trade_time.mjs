import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import vm from 'node:vm';

const box = {};
const context = vm.createContext({render(){}, $(){return box}, esc:String});
vm.runInContext(fs.readFileSync('docs/managed-accounts.js','utf8'), context);

test('trade timestamps use compact Bangkok dates and 24-hour midnight',()=>{
  for (const [input, expected] of [
    ['2026-09-01T15:10:00Z','26,09,01 22:10'],
    ['2026-09-01T17:00:00Z','26,09,02 00:00'],
    ['2026-12-31T18:05:00Z','27,01,01 01:05'],
    ['2026-09-01T22:10:00+07:00','26,09,01 22:10'],
    [null,'확인 기록 없음'], ['', '확인 기록 없음'], ['invalid','확인 기록 없음']
  ]) assert.equal(context.maTradeTime(input),expected);
});

test('history renders entry and actual close dates without inventing an open-trade exit',async()=>{
  context.maRequest = async()=>({rows:[
    {symbol:'BTC',side:'long',status:'closed',control_marker:2,opened_at:'2026-09-01T15:10:00Z',closed_at:'2026-09-01T16:45:00Z',margin_usdt:25,realized_pnl_usdt:1},
    {symbol:'ETH',side:'long',status:'open',control_marker:1,created_at:'2026-09-01T17:00:00Z'}
  ]});
  await context.maTrades('test');
  assert.match(box.innerHTML,/진입 26,09,01 22:10<br>청산 26,09,01 23:45/);
  assert.match(box.innerHTML,/진입 26,09,02 00:00/);
  assert.equal((box.innerHTML.match(/<br>청산 /g)||[]).length,1);
  assert.match(box.innerHTML,/담보금 \$25\.00/);
  assert.match(box.innerHTML,/>2<\/sup>/);
  assert.match(box.innerHTML,/진행 중/);
});

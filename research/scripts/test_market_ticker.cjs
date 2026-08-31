const {test}=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const vm=require('node:vm');
const html=fs.readFileSync('docs/index.html','utf8');
const fn=html.slice(html.indexOf('function renderMarket(){'),html.indexOf('\nfunction kst('));
function render(usdt){const node={innerHTML:''};const context={DATA:{market:{USDT:usdt}},$:()=>node,marketMoney:v=>v.currency==='KRW'?'₩'+v.price:'$'+v.price,Date,Number};vm.createContext(context);vm.runInContext(fn+';renderMarket();',context);return node.innerHTML;}
test('Upbit KRW USDT is the sixth ticker and uses the existing snapshot',()=>{const s=render({price:1399,change:0,source:'Upbit',currency:'KRW',updated:new Date().toISOString()});assert.equal((s.match(/data-market=/g)||[]).length,6);assert(s.indexOf('data-market="USDT"')>s.indexOf('data-market="SOL"'));assert.match(s,/업비트 · 원화/);assert.match(s,/₩1399/);assert.match(s,/\+0.00%/);assert.doesNotMatch(fn,/fetch\(/);});
test('missing, invalid or wrong-source USDT never displays a made-up price',()=>{for(const data of [undefined,{price:0},{price:NaN},{price:1399,source:'Other',currency:'KRW'}]){const s=render(data);assert.match(s,/조회 대기/);assert.doesNotMatch(s,/₩/);}});
test('stale USDT retains its quote with an explicit delayed label',()=>{const s=render({price:1399,change:1,source:'Upbit',currency:'KRW',updated:new Date(Date.now()-240000).toISOString()});assert.match(s,/₩1399/);assert.match(s,/갱신 지연/);assert.doesNotMatch(s,/\+1.00%/);});

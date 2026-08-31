import assert from 'node:assert/strict';
import {combinationDecision} from '../../supabase/functions/_shared/plan_b_combination.mjs';
let input='';for await(const chunk of process.stdin)input+=chunk;
const outcomes=[];
for(const {symbol,rows,expected} of JSON.parse(input)){
 let checked=0,gaps=0,signals=0;
 for(let i=169;i<rows.length-1;i++){
  const sample=rows.slice(i-169,i+1),now=rows[i].t+3600000;
  if(sample.at(-1).t-sample[0].t!==169*3600000){gaps++;assert.throws(()=>combinationDecision(symbol,sample,now));continue;}
  const d=combinationDecision(symbol,sample,now),side=d.side==='long'?1:d.side==='short'?-1:0;
  assert.equal(side,expected[i],`${symbol} ${now}`);checked++;signals+=side!==0;
 }
 outcomes.push({symbol,checked,gap_windows_rejected:gaps,raw_signals:signals});
}
process.stdout.write(JSON.stringify({pass:true,outcomes,total_checked:outcomes.reduce((s,x)=>s+x.checked,0)}));

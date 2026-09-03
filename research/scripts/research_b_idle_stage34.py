"""Research only: allocation search over the three cross-third-positive Stage32 rules."""
import itertools,json
from datetime import datetime,timezone
import research_b_idle_stage32 as p

s=p.s; OUT=s.core.RESULT_DIR/'b_idle_stage34'
RULES={
 'LINK':('exhaust_n3_move0.05',3),
 'DOT':('capitulation_n12_move0.05_vol3.0_wick0.5',3),
 'LTC':('exhaust_n5_move0.05',3),
}

def main():
 OUT.mkdir(exist_ok=True)
 series,entries,times,standard=p.current_stage26();run=p.weighted_replay()
 base=run(series,entries,times,1.15);stress_base=run(series,entries,times,1.15,cost_mult=2)
 assert abs(base['return_pct']-standard['reference']['return_pct'])<1e-6
 busy=set()
 for t,ps in entries.items():
  for x in ps:busy.update(range(t,x['exit_bar']+3600000,3600000))
 ops={}
 for symbol,(name,lev) in RULES.items():
  rows=s.core.read_candles(s.core.DATA_DIR/f'{symbol}USDT_1h.csv')
  for r in rows:r['symbol']=symbol
  series[symbol]={r['t']:r for r in rows}
  sig=dict(p.candidate_patterns(rows))[name]
  ops[symbol]=s.opportunities(rows,sig,1,lev,busy)
 cuts=[times[0]+int((times[-1]+3600000-times[0])*k/3) for k in range(4)]
 allocations=[]
 for pair in itertools.combinations(RULES,2):
  for a in (.1,.15,.2,.25,.3):allocations.append({pair[0]:a,pair[1]:.4-a})
 for vals in ((.2,.1,.1),(.1,.2,.1),(.1,.1,.2),(.2,.2,.2),(.3,.15,.15),(.15,.3,.15),(.15,.15,.3)):
  allocations.append(dict(zip(RULES,vals)))
 results=[]
 for alloc in allocations:
  ee={t:[dict(x) for x in ps] for t,ps in entries.items()}
  for symbol,frac in alloc.items():
   for x in ops[symbol]:ee.setdefault(x['entry_ts'],[]).append({**x,'weight_scale':frac/1.15})
  full=run(series,ee,times,1.15);stress=run(series,ee,times,1.15,cost_mult=2)
  seg=[p.compact(run(series,ee,times,1.15,start=cuts[k],end=cuts[k+1])) for k in range(3)]
  extra=[x for x in full['ledger'] if x['symbol'] in alloc];base_rows=[x for x in full['ledger'] if x['symbol'] in p.CURRENT_B]
  overlap=sum(any(x['entry_ts']<z['exit_ts'] and x['exit_ts']>z['entry_ts'] for z in base_rows) for x in extra);assert overlap==0
  passed=full['return_pct']>base['return_pct'] and stress['return_pct']>stress_base['return_pct'] and full['hourly_mark_mdd_pct']>=-70 and not full['liquidation_proxy_count'] and not stress['liquidation_proxy_count'] and all(z['return_pct']>0 for z in seg)
  results.append(dict(allocation=alloc,total_fraction=sum(alloc.values()),full=p.compact(full),double_cost=p.compact(stress),segments=seg,extra_trades=len(extra),overlap=overlap,passed=passed))
 results.sort(key=lambda x:(x['passed'],x['full']['return_pct']),reverse=True)
 out=dict(id='B-IDLE-STAGE34',generated_at=datetime.now(timezone.utc).isoformat(),research_only=True,baseline=p.compact(base),tested=len(results),results=results,limitations=['All thirds used for comparison; no untouched holdout','Research only; no live deployment'])
 (OUT/'results.json').write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf8')
 print(json.dumps({'passes':sum(x['passed'] for x in results),'best':results[0]},ensure_ascii=False),flush=True)
if __name__=='__main__':main()

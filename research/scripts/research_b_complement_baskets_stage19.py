"""Compare fixed 25% supplemental budget across one-hour candidates. Research only."""
import json,inspect
from datetime import datetime,timezone
import research_b_complement_stage17 as s

def main():
 series,entries,times=s.b.prepare();busy=set()
 for t,ps in entries.items():
  for p in ps:busy.update(range(t,p['exit_bar']+3600000,3600000))
 src=inspect.getsource(s.b.replay).replace('target*(1+x','target*x.get("weight_scale",1.)*(1+x').replace('margin = target*shrink','margin = target*shrink*x.get("weight_scale",1.)')
 env=dict(s.b.__dict__);exec(src,env);run=env['replay']
 candidates={}
 for symbol,n,lev in [('XRP',3,3),('ALGO',7,3),('DOT',7,3)]:
  rows=s.core.read_candles(s.core.DATA_DIR/f'{symbol}USDT_1h.csv')
  for r in rows:r['symbol']=symbol
  series[symbol]={r['t']:r for r in rows}
  sig=next(sig for name,sig in s.patterns(rows) if name==f'streak_exhaustion_n{n}_move0.03')
  candidates[symbol]=s.opportunities(rows,sig,1,lev,busy)
 cuts=[times[0]+int((times[-1]+3600000-times[0])*k/3) for k in range(4)]
 base=s.compact(run(series,entries,times,1.15));stress_base=s.compact(run(series,entries,times,1.15,cost_mult=2));results=[]
 for combo in [('XRP','ALGO'),('XRP','DOT'),('ALGO','DOT'),('XRP','ALGO','DOT')]:
  e={t:[dict(x) for x in ps] for t,ps in entries.items()}
  for symbol in combo:
   for p in candidates[symbol]:e.setdefault(p['entry_ts'],[]).append({**p,'weight_scale':.25/len(combo)/1.15})
  full=run(series,e,times,1.15);stress=run(series,e,times,1.15,cost_mult=2)
  seg=[s.compact(run(series,e,times,1.15,start=cuts[i],end=cuts[i+1])) for i in range(3)]
  a=[x for x in full['ledger'] if x['symbol'] in s.b.SYMBOLS];extra=[x for x in full['ledger'] if x['symbol'] in combo]
  overlaps=sum(any(x['entry_ts']<z['exit_ts'] and x['exit_ts']>z['entry_ts'] for z in a) for x in extra)
  assert overlaps==0
  result=dict(symbols=combo,total_extra_target_fraction=.25,full=s.compact(full),double_cost=s.compact(stress),segments=seg,extra_trades=len(extra),holding_overlap_trades=overlaps,passes_cost_stress=stress['return_pct']>stress_base['return_pct'])
  results.append(result);print(json.dumps(result),flush=True)
 output=dict(id='B-COMPLEMENT-STAGE19-BASKETS',generated_at=datetime.now(timezone.utc).isoformat(),baseline=base,baseline_stress=stress_base,results=results,independent_validation=False)
 (s.core.RESULT_DIR/'b_complement_stage18_1h'/'baskets.json').write_text(json.dumps(output,indent=2),encoding='utf8')
if __name__=='__main__':main()

"""Delay, quantity-grid, and ordered synthetic validation for A Stage119. Research only."""
from __future__ import annotations
import json, statistics
from datetime import datetime, timezone

import research_a_drawdown_guard_stage75 as a75
import research_ab_reinforcement_stage113 as s113
import research_a_sol_short_refinement_stage115 as s115
import research_a_delta_notional_stage119 as s119

OUT=s115.ab.OUT/"A_STAGE121_DELTA_NOTIONAL_EXECUTION_VALIDATION.json"; END=s115.END; H=s115.H
T=.015
def c(x): return s119.compact(x)
def delay(m): return {s:{t+H:v for t,v in rows.items()} for s,rows in m.items()}

def main():
 maps,bars,funding=s113.a_inputs(); start=min(set.intersection(*(set(bars[s]) for s in s115.a68.SYMBOLS)))
 guarded=s115.filtered(maps,bars,.035,.12,3,0); delayed=delay(guarded)
 delay_base=s119.run(delayed,bars,funding,start,END,0)
 delay_candidate=s119.run(delayed,bars,funding,start,END,T)
 delay_triple=s119.run(delayed,bars,funding,start,END,T,.0012,.005)
 paths=[]
 for market in a75.synthetic_markets():
  gm=s115.filtered(market['maps'],market['bars'],.035,.12,3,0)
  base=s119.run(gm,market['bars'],market['funding'],market['start'],market['end'],0)
  cand=s119.run(gm,market['bars'],market['funding'],market['start'],market['end'],T)
  double=s119.run(gm,market['bars'],market['funding'],market['start'],market['end'],T,.0008,.003)
  triple=s119.run(gm,market['bars'],market['funding'],market['start'],market['end'],T,.0012,.005)
  paths.append({'window':market['window'],'replicate':market['replicate'],'seed':market['seed'],
   'baseline':c(base),'candidate':c(cand),'double':c(double),'triple':c(triple)})
  print('path',len(paths),flush=True)
 def summary(key):
  vals=[x[key]['return_pct'] for x in paths]
  return {'profitable':sum(x[key]['end_usd']>100 for x in paths),'mdd_within_70':sum(x[key]['hourly_adverse_bound_mdd_pct']>=-70 for x in paths),
   'return_min':min(vals),'return_median':statistics.median(vals),'return_mean':statistics.mean(vals),'return_max':max(vals)}
 result={'id':'A-STAGE121-DELTA-NOTIONAL-EXECUTION-VALIDATION','generated_at':datetime.now(timezone.utc).isoformat(),
  'research_only':True,'live_changes':False,'candidate':{'minimum_delta_pct_of_equity':1.5,'entry_exit_reversal_delayed':False},
  'one_hour_signal_delay':{'baseline':c(delay_base),'candidate':c(delay_candidate),'candidate_triple':c(delay_triple)},
  'quantity_grid':{'applied':True,'source':'Current BingX precision/minimum/minimum-USDT rules in validate_a_scale_stop_stage70.rounded_qty'},
  'ordered_synthetic':{'paths':len(paths),'baseline':summary('baseline'),'candidate':summary('candidate'),'double':summary('double'),'triple':summary('triple'),
   'candidate_beats_baseline':sum(x['candidate']['end_usd']>x['baseline']['end_usd'] for x in paths),'details':paths},
  'checks':{},'limitations':['Ordered synthetic paths perturb prior chronological markets and are not independent future data.',
   'One-hour delay applies to the complete daily target as an execution stress, while normal operation remains immediate.',
   'Historical current contract-grid rules may differ from past exchange rules.']}
 o=result['ordered_synthetic']; d=result['one_hour_signal_delay']
 result['checks']={'delayed_candidate_beats_delayed_baseline':d['candidate']['return_pct']>d['baseline']['return_pct'],
  'delayed_triple_over_1m':d['candidate_triple']['return_pct']>=1_000_000,
  'all_synthetic_profitable':o['candidate']['profitable']==o['paths'],
  'all_synthetic_double_profitable':o['double']['profitable']==o['paths'],
  'all_synthetic_triple_profitable':o['triple']['profitable']==o['paths'],
  'all_synthetic_mdd_within_70':o['triple']['mdd_within_70']==o['paths']}
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'delay':result['one_hour_signal_delay'],'synthetic':{k:v for k,v in o.items() if k!='details'},'checks':result['checks']},ensure_ascii=False))
if __name__=='__main__':main()

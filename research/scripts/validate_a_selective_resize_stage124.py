"""Final robustness checks for the Stage123 selective A resize candidate. Research only."""
from __future__ import annotations
import json,statistics
from datetime import datetime,timezone
import research_a_drawdown_guard_stage75 as a75
import research_ab_reinforcement_stage113 as s113
import research_a_sol_short_refinement_stage115 as s115
import research_a_selective_resize_combinations_stage123 as s123
OUT=s115.ab.OUT/'A_STAGE124_SELECTIVE_RESIZE_ROBUSTNESS.json';END=s115.END;H=s115.H
RULES=[('SOL','long','decrease'),('SOL','short','decrease'),('ETH','long','increase'),('BTC','short','decrease')]
def c(x):return{k:v for k,v in x.items()if k not in('stop_events','ledger')}
def shift(m):return{s:{t+H:v for t,v in rows.items()}for s,rows in m.items()}
def main():
 maps,bars,funding=s113.a_inputs();start=min(set.intersection(*(set(bars[s])for s in s115.a68.SYMBOLS)));g=s115.filtered(maps,bars,.035,.12,3,0)
 cuts=[start+(END-start)*i//3 for i in range(4)];thirds=[]
 for i in range(3):
  base=s123.run(g,bars,funding,cuts[i],cuts[i+1],[]);cand=s123.run(g,bars,funding,cuts[i],cuts[i+1],RULES);triple=s123.run(g,bars,funding,cuts[i],cuts[i+1],RULES,.0012,.005)
  thirds.append({'part':i+1,'baseline':c(base),'candidate':c(cand),'candidate_triple':c(triple)})
 dg=shift(g);delay_base=s123.run(dg,bars,funding,start,END,[]);delay_cand=s123.run(dg,bars,funding,start,END,RULES);delay3=s123.run(dg,bars,funding,start,END,RULES,.0012,.005)
 paths=[]
 for market in a75.synthetic_markets():
  gm=s115.filtered(market['maps'],market['bars'],.035,.12,3,0)
  b=s123.run(gm,market['bars'],market['funding'],market['start'],market['end'],[])
  x=s123.run(gm,market['bars'],market['funding'],market['start'],market['end'],RULES)
  x2=s123.run(gm,market['bars'],market['funding'],market['start'],market['end'],RULES,.0008,.003)
  x3=s123.run(gm,market['bars'],market['funding'],market['start'],market['end'],RULES,.0012,.005)
  paths.append({'window':market['window'],'replicate':market['replicate'],'seed':market['seed'],'baseline':c(b),'candidate':c(x),'double':c(x2),'triple':c(x3)});print('path',len(paths),flush=True)
 def sm(k):
  v=[x[k]['return_pct']for x in paths];return{'profitable':sum(x[k]['end_usd']>100 for x in paths),'mdd_within_70':sum(x[k]['hourly_adverse_bound_mdd_pct']>=-70 for x in paths),'min':min(v),'median':statistics.median(v),'mean':statistics.mean(v),'max':max(v)}
 syn={'paths':len(paths),'baseline':sm('baseline'),'candidate':sm('candidate'),'double':sm('double'),'triple':sm('triple'),'candidate_beats_baseline':sum(x['candidate']['end_usd']>x['baseline']['end_usd']for x in paths),'details':paths}
 checks={'all_thirds_profitable':all(x['candidate']['end_usd']>100 for x in thirds),'all_triple_thirds_profitable':all(x['candidate_triple']['end_usd']>100 for x in thirds),'candidate_beats_baseline_all_thirds':all(x['candidate']['end_usd']>x['baseline']['end_usd']for x in thirds),'delayed_candidate_beats_baseline':delay_cand['return_pct']>delay_base['return_pct'],'delayed_triple_over_1m':delay3['return_pct']>=1_000_000,'all_synthetic_profitable':syn['candidate']['profitable']==syn['paths'],'all_synthetic_triple_profitable':syn['triple']['profitable']==syn['paths'],'all_synthetic_triple_mdd_within_70':syn['triple']['mdd_within_70']==syn['paths'],'synthetic_beats_baseline_majority':syn['candidate_beats_baseline']>=17}
 result={'id':'A-STAGE124-SELECTIVE-RESIZE-ROBUSTNESS','generated_at':datetime.now(timezone.utc).isoformat(),'research_only':True,'live_changes':False,'rules':[list(x)for x in RULES],'thirds':thirds,'one_hour_delay':{'baseline':c(delay_base),'candidate':c(delay_cand),'candidate_triple':c(delay3)},'ordered_synthetic':syn,'checks':checks,'pass':all(checks.values()),'limitations':['Perturbed historical paths are not independent future data.','The candidate groups were selected on the historical sample.']}
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'thirds':[{'part':x['part'],'base':x['baseline']['return_pct'],'candidate':x['candidate']['return_pct'],'triple':x['candidate_triple']['return_pct']}for x in thirds],'delay':result['one_hour_delay'],'synthetic':{k:v for k,v in syn.items()if k!='details'},'checks':checks,'pass':result['pass']},ensure_ascii=False))
if __name__=='__main__':main()

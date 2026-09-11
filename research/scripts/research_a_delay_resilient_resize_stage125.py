"""Repair Stage124 delay/cost weakness using smaller selective rule sets. Research only."""
from __future__ import annotations
import itertools,json
from datetime import datetime,timezone
import research_ab_reinforcement_stage113 as s113
import research_a_sol_short_refinement_stage115 as s115
import research_a_selective_resize_combinations_stage123 as s123
OUT=s115.ab.OUT/'A_STAGE125_DELAY_RESILIENT_RESIZE.json';END=s115.END;H=s115.H
ALL=[('SOL','long','decrease'),('SOL','short','decrease'),('ETH','long','increase'),('BTC','short','decrease')]
def c(x):return{k:v for k,v in x.items()if k not in('stop_events','ledger')}
def shift(m):return{s:{t+H:v for t,v in rows.items()}for s,rows in m.items()}
def run(m,b,f,start,end,rules,t,fee=.0004,slip=.001):return s123.R(m,b,f,1.4,.15,start=start,end=end,fee=fee,stop_slippage=slip,dd_trigger=.35,dd_reduced_scale=.75,dd_recovery=.175,resize_filters=set(rules),min_delta_equity_fraction=t)
def main():
 maps,bars,funding=s113.a_inputs();start=min(set.intersection(*(set(bars[s])for s in s115.a68.SYMBOLS)));g=s115.filtered(maps,bars,.035,.12,3,0);dg=shift(g)
 configs=[]
 for n in (2,3):
  for rules in itertools.combinations(ALL,n):
   for t in (.0075,.01,.0125,.015):configs.append((rules,t))
 rows=[]
 for rules,t in configs:
  full=run(g,bars,funding,start,END,rules,t);triple=run(g,bars,funding,start,END,rules,t,.0012,.005)
  delay=run(dg,bars,funding,start,END,rules,t);delay3=run(dg,bars,funding,start,END,rules,t,.0012,.005)
  passed=full['return_pct']>=4_937_714 and triple['return_pct']>=1_000_000 and delay['return_pct']>=5_746_804 and delay3['return_pct']>=1_000_000 and max(full['hourly_adverse_bound_mdd_pct'],delay['hourly_adverse_bound_mdd_pct'])>=-55
  rows.append({'rules':[list(x)for x in rules],'threshold_pct':t*100,'full':c(full),'triple':c(triple),'delay':c(delay),'delay_triple':c(delay3),'screen_pass':passed})
  print(len(rows),n,t,round(full['return_pct']),round(triple['return_pct']),round(delay3['return_pct']),passed,flush=True)
 ranked=sorted(rows,key=lambda x:(x['screen_pass'],min(x['triple']['return_pct'],x['delay_triple']['return_pct']),x['full']['return_pct']),reverse=True)
 for x in ranked[:8]:
  rules=[tuple(z)for z in x['rules']];t=x['threshold_pct']/100
  x['five']=c(run(g,bars,funding,s113.CUT,END,rules,t));x['double']=c(run(g,bars,funding,start,END,rules,t,.0008,.003))
  x['pass']=x['screen_pass'] and x['five']['return_pct']>=4_000_000 and x['double']['return_pct']>=2_000_000
 result={'id':'A-STAGE125-DELAY-RESILIENT-RESIZE','generated_at':datetime.now(timezone.utc).isoformat(),'research_only':True,'live_changes':False,'screens':len(rows),'screen_passing':sum(x['screen_pass']for x in rows),'ranked':ranked,'limitations':['Same historical sample; ordered synthetic validation remains required for finalists.']}
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'passing':sum(bool(x.get('pass'))for x in ranked),'top':ranked[:5]},ensure_ascii=False))
if __name__=='__main__':main()

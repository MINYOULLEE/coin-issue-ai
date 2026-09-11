"""Improve Stage115 cost resilience without weakening its causal guard."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import research_a_drawdown_guard_stage75 as a75
import research_ab_reinforcement_stage113 as s113
import research_a_sol_short_refinement_stage115 as s115
import validate_a_scale_stop_stage70 as s70

OUT=s115.ab.OUT/"A_STAGE117_COST_RESILIENCE.json"; H=s115.H; END=s115.END
CFG={"id":"guard35_075","scale":1.4,"dd_trigger":.35,"dd_reduced_scale":.75,"dd_recovery":.175}
def compact(x): return {k:v for k,v in x.items() if k not in ("stop_events","ledger")}
def normal(m,b,f,start,end): return a75.run(m,b,f,CFG,start=start,end=end)
def cost(m,b,f,start,end,fee,slip):
 return s70.replay(m,b,f,1.4,.15,start=start,end=end,fee=fee,stop_slippage=slip,
  dd_trigger=.35,dd_reduced_scale=.75,dd_recovery=.175)

def main():
 maps,bars,funding=s113.a_inputs(); start=min(set.intersection(*(set(bars[s]) for s in s115.a68.SYMBOLS)))
 baseline_five=normal(maps,bars,funding,s113.CUT,END); baseline_full=normal(maps,bars,funding,start,END)
 screened=[]
 for btc in (.025,.03,.035):
  for sol in (.08,.10,.12):
   for breadth in (3,4,5):
    for multiplier in (0,.25,.5):
     changed=s115.filtered(maps,bars,btc,sol,breadth,multiplier)
     full=normal(changed,bars,funding,start,END); five=normal(changed,bars,funding,s113.CUT,END)
     if full["return_pct"]<4_000_000 or five["return_pct"]<baseline_five["return_pct"] or full["close_mark_mdd_pct"] < -55: continue
     screened.append({"btc_pct":btc*100,"sol_pct":sol*100,"breadth":breadth,"short_multiplier":multiplier,
      "five":compact(five),"full":compact(full)})
 for row in screened:
  changed=s115.filtered(maps,bars,row["btc_pct"]/100,row["sol_pct"]/100,row["breadth"],row["short_multiplier"])
  row["double_full"]=compact(cost(changed,bars,funding,start,END,.0008,.003))
  row["triple_full"]=compact(cost(changed,bars,funding,start,END,.0012,.005))
  row["triple_five"]=compact(cost(changed,bars,funding,s113.CUT,END,.0012,.005))
  row["pass_triple"]=(row["triple_full"]["return_pct"]>=1_000_000 and row["triple_five"]["return_pct"]>=1_000_000
                      and row["triple_full"]["hourly_adverse_bound_mdd_pct"]>=-70)
 ranked=sorted(screened,key=lambda x:(x["pass_triple"],x["triple_full"]["return_pct"],x["full"]["return_pct"]),reverse=True)
 result={"id":"A-STAGE117-COST-RESILIENCE","generated_at":datetime.now(timezone.utc).isoformat(),"research_only":True,"live_changes":False,
  "screen_count":81,"normal_gate_pass":len(screened),"triple_pass":sum(x["pass_triple"] for x in screened),
  "baseline":{"five":compact(baseline_five),"full":compact(baseline_full)},"ranked":ranked,
  "limitations":["Cost stress multiplies modeled fees and stop slippage; it is not an exchange fee forecast.",
   "The grid is local to the Stage115 causal family and remains historical research."]}
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({"normal_gate_pass":len(screened),"triple_pass":result["triple_pass"],"top":ranked[:10]},ensure_ascii=False))
if __name__=="__main__": main()

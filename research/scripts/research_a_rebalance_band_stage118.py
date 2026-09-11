"""Causal no-trade bands for the Stage117 A candidate. Research only."""
from __future__ import annotations
import json
from datetime import datetime, timezone
import research_ab_reinforcement_stage113 as s113
import research_a_sol_short_refinement_stage115 as s115
import research_a_cost_resilience_stage117 as s117

OUT=s115.ab.OUT/"A_STAGE118_REBALANCE_BAND.json"; H=s115.H; END=s115.END

def compress(maps,tolerance,refresh_days):
 out={}
 for symbol,rows in maps.items():
  kept={}; last_value=None; last_time=None
  for stamp,value in sorted(rows.items()):
   changed=last_value is None or (value==0)!=(last_value==0) or value*last_value<0 or abs(value-last_value)>=tolerance
   refresh=last_time is None or stamp-last_time>=refresh_days*24*H
   if changed or refresh:
    kept[stamp]=value;last_value=value;last_time=stamp
  out[symbol]=kept
 return out

def main():
 maps,bars,funding=s113.a_inputs();start=min(set.intersection(*(set(bars[s]) for s in s115.a68.SYMBOLS)))
 guarded=s115.filtered(maps,bars,.035,.12,3,0)
 base=s117.normal(guarded,bars,funding,start,END)
 rows=[]
 for tolerance in (.001,.02,.05,.10,.20):
  for refresh in (2,3,7,14):
   changed=compress(guarded,tolerance,refresh)
   full=s117.normal(changed,bars,funding,start,END);five=s117.normal(changed,bars,funding,s113.CUT,END)
   double=s117.cost(changed,bars,funding,start,END,.0008,.003)
   triple=s117.cost(changed,bars,funding,start,END,.0012,.005)
   rows.append({"target_change_tolerance":tolerance,"forced_refresh_days":refresh,
    "full":s117.compact(full),"five":s117.compact(five),"double":s117.compact(double),"triple":s117.compact(triple),
    "order_reduction_pct":(1-full["total_order_events"]/base["total_order_events"])*100,
    "pass":full["return_pct"]>=base["return_pct"] and five["return_pct"]>=4_000_000
      and double["return_pct"]>=2_000_000 and triple["return_pct"]>=1_000_000
      and full["hourly_adverse_bound_mdd_pct"]>=-55})
 ranked=sorted(rows,key=lambda x:(x["pass"],x["triple"]["return_pct"],x["full"]["return_pct"]),reverse=True)
 result={"id":"A-STAGE118-REBALANCE-BAND","generated_at":datetime.now(timezone.utc).isoformat(),"research_only":True,"live_changes":False,
  "candidate":"Stage117 BTC3.5/SOL12/breadth3 SOL-short block","baseline":s117.compact(base),"screens":len(rows),
  "passing":sum(x["pass"] for x in rows),"ranked":ranked,
  "limitations":["Band compares causal target weights only; it cannot see future prices.",
   "Skipping a rebalance also delays equity-compounding quantity refresh until the forced interval.",
   "Historical results are not live fill validation."]}
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({"passing":result["passing"],"top":ranked[:8]},ensure_ascii=False))
if __name__=="__main__":main()

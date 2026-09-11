"""Robustness checks for Stage119 A delta-notional candidates. Research only."""
from __future__ import annotations
import json
from datetime import datetime, timezone

import research_ab_reinforcement_stage113 as s113
import research_a_sol_short_refinement_stage115 as s115
import research_a_delta_notional_stage119 as s119

OUT=s115.ab.OUT/"A_STAGE120_DELTA_NOTIONAL_ROBUSTNESS.json"; END=s115.END

def c(x): return s119.compact(x)

def main():
 maps,bars,funding=s113.a_inputs(); start=min(set.intersection(*(set(bars[s]) for s in s115.a68.SYMBOLS)))
 guarded=s115.filtered(maps,bars,.035,.12,3,0)
 cuts=[start+(END-start)*i//3 for i in range(4)]
 rows=[]
 for threshold in (.0125,.015,.0175,.02,.0225,.025):
  full=s119.run(guarded,bars,funding,start,END,threshold)
  five=s119.run(guarded,bars,funding,s113.CUT,END,threshold)
  double=s119.run(guarded,bars,funding,start,END,threshold,.0008,.003)
  triple=s119.run(guarded,bars,funding,start,END,threshold,.0012,.005)
  thirds=[s119.run(guarded,bars,funding,cuts[i],cuts[i+1],threshold) for i in range(3)]
  stress_thirds=[s119.run(guarded,bars,funding,cuts[i],cuts[i+1],threshold,.0012,.005) for i in range(3)]
  passed=(five['return_pct']>=4_000_000 and full['return_pct']>=4_937_714 and double['return_pct']>=2_000_000
          and triple['return_pct']>=1_000_000 and full['hourly_adverse_bound_mdd_pct']>=-55
          and all(x['end_usd']>100 and x['hourly_adverse_bound_mdd_pct']>=-70 for x in thirds+stress_thirds))
  rows.append({'minimum_delta_pct_of_equity':threshold*100,'full':c(full),'five':c(five),'double':c(double),'triple':c(triple),
   'thirds':[c(x) for x in thirds],'triple_cost_thirds':[c(x) for x in stress_thirds],'pass':passed})
  print(threshold,passed,[round(x['return_pct'],1) for x in thirds],[round(x['return_pct'],1) for x in stress_thirds],flush=True)
 ranked=sorted(rows,key=lambda x:(x['pass'],x['triple']['return_pct'],x['full']['return_pct']),reverse=True)
 result={'id':'A-STAGE120-DELTA-NOTIONAL-ROBUSTNESS','generated_at':datetime.now(timezone.utc).isoformat(),
  'research_only':True,'live_changes':False,'screens':len(rows),'passing':sum(x['pass'] for x in rows),'ranked':ranked,
  'limitations':['Chronological thirds reset equity to $100 and are robustness checks, not additive portfolio returns.',
   'The same historical sample informed the neighborhood; future performance is unknown.']}
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'passing':result['passing'],'top':ranked[:3]},ensure_ascii=False))
if __name__=='__main__':main()

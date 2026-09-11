"""Corrected A guard search: dd_reduced_scale is a multiplier, not an absolute exposure."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import validate_a_exposure_scale_stage68 as s68
import validate_a_scale_stop_stage70 as s70

OUT=Path(__file__).resolve().parents[1]/"results"/"a_stage77_corrected_guard"
BASE_RET=2_143_508.58; BASE_STRESS=1_033_997.04

def compact(x):return {k:v for k,v in x.items() if k!="ledger"}

def main():
 maps,bars,funding=s68.load();times=sorted(set.intersection(*[set(bars[s]) for s in s68.SYMBOLS]));cuts=[times[0]+int((times[-1]-times[0])*i/3) for i in range(4)]
 rows=[];tested=0
 for scale in (1.40,1.45,1.50,1.55,1.60):
  for stop in (.12,.15):
   for trigger in (.25,.30,.35):
    for factor in (.40,.50,.60,.70,.75):
     tested+=1;kw={"dd_trigger":trigger,"dd_reduced_scale":factor,"dd_recovery":trigger/2}
     base=compact(s70.replay(maps,bars,funding,scale,stop,**kw))
     if base["return_pct"]<=BASE_RET or base["max_simultaneous_adverse_margin_equity_ratio_at_3x"]>.95:continue
     stress=compact(s70.replay(maps,bars,funding,scale,stop,fee=.0008,stop_slippage=.003,**kw))
     severe=compact(s70.replay(maps,bars,funding,scale,stop,fee=.0015,stop_slippage=.01,**kw))
     thirds=[compact(s70.replay(maps,bars,funding,scale,stop,start=cuts[i],end=cuts[i+1],**kw)) for i in range(3)]
     passed=(stress["return_pct"]>BASE_STRESS and severe["end_usd"]>100
       and stress["max_simultaneous_adverse_margin_equity_ratio_at_3x"]<=.95
       and severe["max_simultaneous_adverse_margin_equity_ratio_at_3x"]<=.95
       and base["hourly_adverse_bound_mdd_pct"]>=-70 and severe["hourly_adverse_bound_mdd_pct"]>=-70
       and all(x["end_usd"]>100 and x["close_mark_mdd_pct"]>=-70 for x in thirds))
     rows.append({"config":{"normal_scale":scale,"stop":stop,"trigger":trigger,"guard_factor":factor,"guard_effective_scale":scale*factor,"recovery":trigger/2},"base":base,"double":stress,"severe":severe,"thirds":thirds,"pass":passed})
     print("candidate",tested,scale,stop,trigger,factor,passed,flush=True)
 rows.sort(key=lambda x:x["base"]["return_pct"],reverse=True)
 out={"id":"A-STAGE77-CORRECTED-GUARD","generated_at":datetime.now(timezone.utc).isoformat(),"research_only":True,"tested":tested,"passing":[x for x in rows if x["pass"]],"top":rows[:20],"parameter_correction":"guard_effective_scale = normal_scale * guard_factor","limitations":["Same 5y signal source","Grid selection bias","Synthetic follow-up required"]}
 OUT.mkdir(parents=True,exist_ok=True);(OUT/"RESULTS.json").write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({"tested":tested,"passing":len(out["passing"]),"top":[{"config":x["config"],"ret":x["base"]["return_pct"],"stress":x["double"]["return_pct"],"severe":x["severe"]["return_pct"],"mdd":x["base"]["close_mark_mdd_pct"],"adverse":x["base"]["hourly_adverse_bound_mdd_pct"],"margin":x["base"]["max_simultaneous_adverse_margin_equity_ratio_at_3x"],"events":x["base"]["total_order_events"],"thirds":[z["return_pct"] for z in x["thirds"]]} for x in out["passing"][:10]]},ensure_ascii=False))

if __name__=="__main__":main()

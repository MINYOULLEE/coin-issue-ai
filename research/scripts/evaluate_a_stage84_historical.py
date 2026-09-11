"""Historical five-year check for frozen Stage84 top concentration overlay."""
from __future__ import annotations
import json
from datetime import datetime,timezone
from pathlib import Path
import research_a_stage78_two_tier_guard as s78
import research_a_stage81_volatility_overlay as s81
import research_a_stage84_signal_concentration as s84
import validate_a_exposure_scale_stage68 as s68
CFG={"min_same":4,"factor":.70,"dd_gate":.20}
OUT=Path(__file__).resolve().parents[1]/"results"/"a_stage84_signal_concentration"/"HISTORICAL.json"
def main():
 maps,bars,funding=s68.load();ov=s84.concentration_overlay(maps,CFG["min_same"],CFG["factor"]);costs={"base":(.0004,.001),"double":(.0008,.003),"severe":(.0015,.01)}
 full={k:s78.replay(maps,bars,funding,**s81.BASE,fee=v[0],stop_slippage=v[1],scale_overlay=ov,overlay_min_drawdown=CFG["dd_gate"]) for k,v in costs.items()}
 times=sorted(set.intersection(*[set(bars[s]) for s in s68.SYMBOLS]));cuts=[times[0]+int((times[-1]-times[0])*i/3) for i in range(4)]
 thirds=[s78.replay(maps,bars,funding,**s81.BASE,start=cuts[i],end=cuts[i+1],scale_overlay=ov,overlay_min_drawdown=CFG["dd_gate"]) for i in range(3)]
 result={"id":"A-STAGE84-HISTORICAL","generated_at":datetime.now(timezone.utc).isoformat(),"research_only":True,"config":CFG,"full":full,"thirds":thirds};OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({"full":{k:{z:x[z] for z in ("return_pct","close_mark_mdd_pct","hourly_adverse_bound_mdd_pct","total_order_events","max_simultaneous_adverse_margin_equity_ratio_at_3x")} for k,x in full.items()},"thirds":[{z:x[z] for z in ("return_pct","close_mark_mdd_pct","hourly_adverse_bound_mdd_pct","total_order_events")} for x in thirds]},ensure_ascii=False))
if __name__=="__main__":main()

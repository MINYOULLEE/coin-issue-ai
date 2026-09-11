"""Historical comparison of the three frozen Stage83 finalists."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import research_a_stage78_two_tier_guard as s78
import research_a_stage81_volatility_overlay as s81
import research_a_stage82_symbol_volatility as s82
import validate_a_exposure_scale_stage68 as s68

CFGS=[{"window":24,"quantile":.75,"factor":.40,"dd_gate":.20},
      {"window":24,"quantile":.75,"factor":.60,"dd_gate":.20},
      {"window":24,"quantile":.75,"factor":.60,"dd_gate":.10}]
OUT=Path(__file__).resolve().parents[1]/"results"/"a_stage83_gated_symbol_volatility"/"ALTERNATIVES.json"

def main():
 maps,bars,funding=s68.load();rows=[]
 for cfg in CFGS:
  ov=s82.symbol_overlay(bars,maps,cfg["window"],cfg["quantile"],cfg["factor"])
  def run(fee,slip):return s78.replay(maps,bars,funding,**s81.BASE,fee=fee,stop_slippage=slip,scale_overlay=ov,overlay_min_drawdown=cfg["dd_gate"])
  base=run(.0004,.001);double=run(.0008,.003);severe=run(.0015,.01)
  rows.append({"config":cfg,"base":base,"double":double,"severe":severe})
  print("checked",cfg,flush=True)
 result={"id":"A-STAGE83-HISTORICAL-ALTERNATIVES","generated_at":datetime.now(timezone.utc).isoformat(),"research_only":True,"rows":rows}
 OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps([{"config":x["config"],"return":x["base"]["return_pct"],"double":x["double"]["return_pct"],"severe":x["severe"]["return_pct"],"mdd":x["base"]["close_mark_mdd_pct"],"adverse":x["base"]["hourly_adverse_bound_mdd_pct"],"margin":x["base"]["max_simultaneous_adverse_margin_equity_ratio_at_3x"],"events":x["base"]["total_order_events"]} for x in rows],ensure_ascii=False))

if __name__=="__main__":main()

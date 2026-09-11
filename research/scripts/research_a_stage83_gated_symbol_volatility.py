"""Conditional symbol-volatility overlay activated only during portfolio drawdown."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
import research_a_stage78_two_tier_guard as s78
import research_a_stage81_volatility_overlay as s81
import research_a_stage82_symbol_volatility as s82

OUT=Path(__file__).resolve().parents[1]/"results"/"a_stage83_gated_symbol_volatility"

def run(path,cfg,cost="base"):
 fee,slip=s81.COSTS[cost]
 ov=s82.symbol_overlay(path["bars"],path["maps"],cfg["window"],cfg["quantile"],cfg["factor"])
 return s78.replay(path["maps"],path["bars"],path["funding"],**s81.BASE,fee=fee,stop_slippage=slip,
  start=path["start"],end=path["end"],scale_overlay=ov,overlay_min_drawdown=cfg["dd_gate"])

def main():
 paths=s81.prepare_paths();discovery=[p for p in paths if p["split"]=="discovery"];grid=[]
 for window,quantile,factor in ((24,.75,.4),(24,.75,.6),(24,.85,.6)):
  for dd_gate in (.10,.20,.30):
   cfg={"window":window,"quantile":quantile,"factor":factor,"dd_gate":dd_gate}
   values=[run(p,cfg) for p in discovery]
   grid.append({"config":cfg,"score":s81.score(values),"discovery":s81.summarize(values)})
   print("grid",cfg,grid[-1]["score"],flush=True)
 grid.sort(key=lambda x:x["score"],reverse=True);finalists=[]
 for candidate in grid[:3]:
  cfg=candidate["config"];splits={}
  for split in ("discovery","validation","final"):
   ps=[p for p in paths if p["split"]==split]
   splits[split]={cost:s81.summarize([run(p,cfg,cost) for p in ps]) for cost in s81.COSTS}
  finalists.append({"config":cfg,"selection_score":candidate["score"],"splits":splits})
 result={"id":"A-STAGE83-GATED-SYMBOL-VOLATILITY","generated_at":datetime.now(timezone.utc).isoformat(),
  "research_only":True,"grid":grid,"finalists":finalists,
  "split_policy":"windows1-2 discovery; window3 validation; window4 final",
  "limitations":["Transformed history, not future data","Funding omitted","Not BingX fills"]}
 OUT.mkdir(parents=True,exist_ok=True);(OUT/"RESULTS.json").write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
 print(json.dumps({"top":finalists},ensure_ascii=False))

if __name__=="__main__":main()

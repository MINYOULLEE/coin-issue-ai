"""Execution-oriented validation for the margin-feasible A Stage76 candidate."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

import research_a_drawdown_guard_stage75 as s75
import validate_a_exposure_scale_stage68 as s68
import validate_a_scale_stop_stage70 as s70

OUT = Path(__file__).resolve().parents[1] / "results" / "a_stage76_grid" / "EXECUTION_SCALE145.json"
CFG = {"scale":1.45,"stop":.15,"dd_trigger":.45,"dd_reduced_scale":1.1,"dd_recovery":.225}


def replay(maps,bars,funding,start=None,end=None,stress="base"):
    costs={"base":(.0004,.001),"double":(.0008,.003),"severe":(.0015,.01)}
    fee,slip=costs[stress]
    return s70.replay(maps,bars,funding,CFG["scale"],CFG["stop"],fee=fee,stop_slippage=slip,
        start=start,end=end,dd_trigger=CFG["dd_trigger"],dd_reduced_scale=CFG["dd_reduced_scale"],
        dd_recovery=CFG["dd_recovery"])


def dist(xs):
    xs=sorted(xs);return {"min":xs[0],"median":statistics.median(xs),"mean":statistics.mean(xs),"max":xs[-1]}


def main():
    maps,bars,funding=s68.load()
    times=sorted(set.intersection(*[set(bars[s]) for s in s68.SYMBOLS]))
    cuts=[times[0]+int((times[-1]-times[0])*i/3) for i in range(4)]
    historical={k:replay(maps,bars,funding,stress=k) for k in ("base","double","severe")}
    thirds={k:[replay(maps,bars,funding,cuts[i],cuts[i+1],k) for i in range(3)] for k in ("base","severe")}
    markets=s75.synthetic_markets();paths=[]
    for i,m in enumerate(markets,1):
        paths.append({k:replay(m["maps"],m["bars"],m["funding"],m["start"],m["end"],k)
                      for k in ("base","double","severe")})
        if i%8==0:print("validated",i,"/",len(markets),flush=True)
    synthetic={"paths":len(paths)}
    for k in ("base","double","severe"):
        synthetic[k]={"profitable":sum(x[k]["end_usd"]>100 for x in paths),
            "mdd_over_70":sum(x[k]["close_mark_mdd_pct"] < -70 for x in paths),
            "adverse_over_70":sum(x[k]["hourly_adverse_bound_mdd_pct"] < -70 for x in paths),
            "return_pct":dist([x[k]["return_pct"] for x in paths]),
            "mdd_pct":dist([x[k]["close_mark_mdd_pct"] for x in paths]),
            "adverse_mdd_pct":dist([x[k]["hourly_adverse_bound_mdd_pct"] for x in paths])}
    h=historical
    passed=(h["base"]["return_pct"]>2_143_508.58 and h["double"]["return_pct"]>1_033_997.04
        and h["severe"]["end_usd"]>100 and h["base"]["max_simultaneous_adverse_margin_equity_ratio_at_3x"]<=.95
        and all(x["end_usd"]>100 and x["close_mark_mdd_pct"]>=-70 for x in thirds["severe"])
        and all(synthetic[k]["profitable"]==len(paths) and synthetic[k]["mdd_over_70"]==0
                and synthetic[k]["adverse_over_70"]==0 for k in synthetic if k!="paths"))
    result={"id":"A-STAGE76-EXECUTION-SCREEN","generated_at":datetime.now(timezone.utc).isoformat(),
        "research_only":True,"config":CFG,"historical":historical,"thirds":thirds,"synthetic":synthetic,
        "pass":passed,"cost_models":{"base":"0.04% turnover + 0.1% stop slippage",
        "double":"0.08% turnover + 0.3% stop slippage","severe":"0.15% turnover + 1.0% stop slippage"},
        "limitations":["Cost stress is a latency/adverse-fill proxy, not full minute entry replay",
        "Current BingX contract grid is applied historically","Synthetic paths are perturbed history, not future data"]}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"pass":passed,"historical":{k:{z:v[z] for z in ("return_pct","close_mark_mdd_pct","hourly_adverse_bound_mdd_pct","max_simultaneous_adverse_margin_equity_ratio_at_3x")} for k,v in h.items()},"synthetic":synthetic},ensure_ascii=False))


if __name__=="__main__":main()

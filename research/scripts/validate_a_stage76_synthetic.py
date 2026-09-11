"""Ordered synthetic validation for selected A Stage76 candidates."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

import research_a_drawdown_guard_stage75 as s75

OUT = Path(__file__).resolve().parents[1] / "results" / "a_stage76_grid" / "SYNTHETIC.json"
CONFIGS = [
    {"id":"stage75", "scale":1.4, "stop":.15, "dd_trigger":.35, "dd_reduced_scale":.75, "dd_recovery":.175},
    {"id":"stage76_balanced", "scale":1.6, "stop":.18, "dd_trigger":.30, "dd_reduced_scale":.70, "dd_recovery":.15},
    {"id":"stage76_high", "scale":1.6, "stop":.18, "dd_trigger":.45, "dd_reduced_scale":1.10, "dd_recovery":.225},
]


def stats(xs):
    xs=sorted(xs)
    return {"min":xs[0],"median":statistics.median(xs),"mean":statistics.mean(xs),"max":xs[-1]}


def run(market, c, stress=False):
    cfg={"scale":c["scale"],"dd_trigger":c["dd_trigger"],
         "dd_reduced_scale":c["dd_reduced_scale"],"dd_recovery":c["dd_recovery"]}
    extra={"fee":.0008,"stop_slippage":.003} if stress else {}
    return s75.s70.replay(market["maps"],market["bars"],market["funding"],
                          cfg["scale"],c["stop"],start=market["start"],end=market["end"],
                          dd_trigger=cfg["dd_trigger"],dd_reduced_scale=cfg["dd_reduced_scale"],
                          dd_recovery=cfg["dd_recovery"],**extra)


def main():
    markets=s75.synthetic_markets()
    results=[]
    for c in CONFIGS:
        paths=[]
        for i,m in enumerate(markets,1):
            paths.append({"base":run(m,c),"stress":run(m,c,True)})
            if i%8==0: print(c["id"],i,"/",len(markets),flush=True)
        row={"config":c,"paths":len(paths),
             "profitable":sum(x["base"]["end_usd"]>100 for x in paths),
             "stress_profitable":sum(x["stress"]["end_usd"]>100 for x in paths),
             "mdd_over_70":sum(x["base"]["close_mark_mdd_pct"] < -70 for x in paths),
             "adverse_over_70":sum(x["base"]["hourly_adverse_bound_mdd_pct"] < -70 for x in paths),
             "stress_mdd_over_70":sum(x["stress"]["close_mark_mdd_pct"] < -70 for x in paths),
             "return_pct":stats([x["base"]["return_pct"] for x in paths]),
             "stress_return_pct":stats([x["stress"]["return_pct"] for x in paths]),
             "mdd_pct":stats([x["base"]["close_mark_mdd_pct"] for x in paths]),
             "adverse_mdd_pct":stats([x["base"]["hourly_adverse_bound_mdd_pct"] for x in paths])}
        results.append(row)
    out={"id":"A-STAGE76-ORDERED-SYNTHETIC","generated_at":datetime.now(timezone.utc).isoformat(),
         "research_only":True,"results":results,
         "limitations":["Perturbed historical paths are not independent future data","No live changes"]}
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False))


if __name__=="__main__": main()

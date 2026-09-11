"""Robustness validation for the frozen Stage115 A candidate. Research only."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone

import evaluate_ab_7y as ab
import research_a_drawdown_guard_stage75 as a75
import research_ab_reinforcement_stage113 as s113
import research_a_sol_short_refinement_stage115 as s115
import validate_a_exposure_scale_stage68 as a68
import validate_a_scale_stop_stage70 as s70

OUT = ab.OUT / "A_STAGE116_SOL_SHORT_ROBUSTNESS.json"
H = ab.H
END = int(datetime(2026, 8, 30, tzinfo=timezone.utc).timestamp()*1000)
CFG = {"id":"guard35_075","scale":1.4,"dd_trigger":.35,"dd_reduced_scale":.75,"dd_recovery":.175}

def compact(x): return {k:v for k,v in x.items() if k not in ("stop_events","ledger")}
def run(m,b,f,start,end,fee=None,slip=None):
    if fee is None: return a75.run(m,b,f,CFG,start=start,end=end)
    return s70.replay(m,b,f,CFG["scale"],.15,start=start,end=end,fee=fee,stop_slippage=slip,
                      dd_trigger=.35,dd_reduced_scale=.75,dd_recovery=.175)
def delayed(maps): return {s:{t+H:v for t,v in rows.items()} for s,rows in maps.items()}

def main():
    maps,bars,funding=s113.a_inputs(); start=min(set.intersection(*(set(bars[s]) for s in a68.SYMBOLS)))
    base=run(maps,bars,funding,start,END)
    candidate=s115.filtered(maps,bars,.03,.10,4,0)
    exact=run(candidate,bars,funding,start,END)
    neighborhood=[]
    for btc in (.025,.03,.035):
      for sol in (.08,.10,.12):
       for breadth in (3,4,5):
        changed=s115.filtered(maps,bars,btc,sol,breadth,0)
        five=run(changed,bars,funding,s113.CUT,END); full=run(changed,bars,funding,start,END)
        neighborhood.append({"btc_pct":btc*100,"sol_pct":sol*100,"breadth":breadth,
          "five_return_pct":five["return_pct"],"full_return_pct":full["return_pct"],
          "full_mdd_pct":full["close_mark_mdd_pct"],"full_adverse_mdd_pct":full["hourly_adverse_bound_mdd_pct"],
          "passes":five["return_pct"]>=1_000_000 and full["return_pct"]>=1_000_000 and full["hourly_adverse_bound_mdd_pct"]>=-70})
    cuts=[start+(END-start)*k//3 for k in range(4)]
    thirds=[]
    for i in range(3):
      b=run(maps,bars,funding,cuts[i],cuts[i+1]); c=run(candidate,bars,funding,cuts[i],cuts[i+1])
      thirds.append({"part":i+1,"baseline":compact(b),"candidate":compact(c)})
    double=run(candidate,bars,funding,start,END,.0008,.003)
    triple=run(candidate,bars,funding,start,END,.0012,.005)
    delayed_maps=delayed(maps); delayed_candidate=s115.filtered(delayed_maps,bars,.03,.10,4,0)
    delay_base=run(delayed_maps,bars,funding,start,END); delay_candidate=run(delayed_candidate,bars,funding,start,END)

    paths=[]
    for market in a75.synthetic_markets():
      bm=run(market["maps"],market["bars"],market["funding"],market["start"],market["end"])
      cm=s115.filtered(market["maps"],market["bars"],.03,.10,4,0)
      cr=run(cm,market["bars"],market["funding"],market["start"],market["end"])
      cs=run(cm,market["bars"],market["funding"],market["start"],market["end"],.0008,.003)
      paths.append({"window":market["window"],"replicate":market["replicate"],"baseline":compact(bm),"candidate":compact(cr),"candidate_stress":compact(cs)})
    returns=[x["candidate"]["return_pct"] for x in paths]; stress=[x["candidate_stress"]["return_pct"] for x in paths]
    result={"id":"A-STAGE116-SOL-SHORT-ROBUSTNESS","generated_at":datetime.now(timezone.utc).isoformat(),
      "research_only":True,"live_changes":False,"candidate":{"btc_168h_min_pct":3,"sol_168h_min_pct":10,"breadth_min":4,"sol_short_multiplier":0},
      "exact":{"baseline":compact(base),"candidate":compact(exact)},"neighborhood":neighborhood,"thirds":thirds,
      "cost_stress":{"double":compact(double),"triple":compact(triple)},
      "one_hour_delay":{"baseline":compact(delay_base),"candidate":compact(delay_candidate)},
      "ordered_synthetic":{"paths":len(paths),"profitable":sum(x["candidate"]["end_usd"]>100 for x in paths),
        "stress_profitable":sum(x["candidate_stress"]["end_usd"]>100 for x in paths),
        "mdd_below_minus70":sum(x["candidate"]["hourly_adverse_bound_mdd_pct"] < -70 for x in paths),
        "return_min":min(returns),"return_median":statistics.median(returns),"stress_return_min":min(stress),"paths_detail":paths},
      "checks":{},"limitations":["Synthetic paths are ordered perturbations of history, not independent future markets.",
        "One-hour delay is conservative relative to the normal daily boundary but still uses hourly OHLC.",
        "The underlying A trees are previously selected, so this is candidate robustness rather than independent future proof."]}
    result["checks"]={
      "exact_reproduced":abs(exact["return_pct"]-4590030.753404408)<1e-6,
      "all_neighbors_survive":all(x["passes"] for x in neighborhood),
      "all_thirds_profitable":all(x["candidate"]["end_usd"]>100 for x in thirds),
      "triple_cost_over_1m":triple["return_pct"]>=1_000_000,
      "delay_candidate_beats_delay_baseline":delay_candidate["return_pct"]>delay_base["return_pct"],
      "all_synthetic_profitable":all(x["candidate"]["end_usd"]>100 for x in paths),
      "all_synthetic_stress_profitable":all(x["candidate_stress"]["end_usd"]>100 for x in paths),
      "synthetic_mdd_within_70":all(x["candidate"]["hourly_adverse_bound_mdd_pct"]>=-70 for x in paths)}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"checks":result["checks"],"exact":result["exact"],"neighbor_min":min(x["full_return_pct"] for x in neighborhood),
      "thirds":[{"part":x["part"],"base":x["baseline"]["return_pct"],"candidate":x["candidate"]["return_pct"]} for x in thirds],
      "double":double["return_pct"],"triple":triple["return_pct"],"delay":{"base":delay_base["return_pct"],"candidate":delay_candidate["return_pct"]},
      "synthetic":{k:v for k,v in result["ordered_synthetic"].items() if k!="paths_detail"}},ensure_ascii=False))

if __name__=="__main__": main()

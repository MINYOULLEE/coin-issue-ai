from __future__ import annotations

import json
from datetime import datetime, timezone
import numpy as np

import replay_mdd30 as core
import combine_novel_patterns as combo

SYMBOLS=("AVAX","ICP","BCH","DOGE","UNI")
BASE=np.array([3.,5.,3.,5.,2.])

def build():
    src=json.loads((core.RESULT_DIR/"novel_pattern_search_stage10.json").read_text(encoding="utf-8"))
    best={x["best"]["symbol"]:x["best"] for x in src["results"] if x["best"]}
    streams={s:combo.trade_stream(best[s]) for s in SYMBOLS};times=sorted(set().union(*(set(v) for v in streams.values())))
    return times,streams

def simulate(times,streams,weights,start,end,cost_mult=1.):
    eq=peak=1.;mdd=0.;trades=wins=0;worst=0.;events=0
    for ts in times:
        if ts<start or ts>=end:continue
        legs=[]
        for i,s in enumerate(SYMBOLS):
            if ts not in streams[s]:continue
            # Stream already contains standard costs; subtract incremental stressed cost.
            ret=streams[s][ts]-(cost_mult-1.)*.0015*BASE[i]
            legs.append(ret*weights[i]);trades+=1;wins+=ret>0
        if not legs:continue
        net=sum(legs);worst=min(worst,net);eq*=max(0.,1+net);peak=max(peak,eq);mdd=min(mdd,eq/peak-1);events+=1
        if eq<=0:break
    return {"multiple":eq,"return_pct":(eq-1)*100,"mdd_pct":mdd*100,"trades":trades,"events":events,
            "win_rate_pct":float(wins/trades*100) if trades else 0.0,"worst_event_pct":float(worst*100),"liquidation_proxy_breached":bool(worst<=-1)}

def main():
    times,streams=build();cuts=(times[0],times[len(times)//3],times[2*len(times)//3],times[-1]+1);rows=[]
    # Equal capital allocation, increasing aggregate aggression. Base strategy leverage remains unchanged.
    for scale in np.arange(3.,8.01,.25):
        w=np.repeat(scale/len(SYMBOLS),len(SYMBOLS));gross=float(w@BASE)
        seg=[simulate(times,streams,w,cuts[k],cuts[k+1]) for k in range(3)]
        full=simulate(times,streams,w,cuts[0],cuts[-1]);stress=simulate(times,streams,w,cuts[0],cuts[-1],2.)
        passed=full["return_pct"]>=1_000_000 and full["mdd_pct"]>=-70 and not full["liquidation_proxy_breached"] and all(x["return_pct"]>0 and x["mdd_pct"]>=-70 and not x["liquidation_proxy_breached"] for x in seg)
        rows.append({"scale":float(scale),"gross_exposure":gross,"segments":seg,"full":full,"double_cost":stress,"passed":bool(passed)})
    passing=[x for x in rows if x["passed"]];best=max(passing,key=lambda x:x["full"]["return_pct"]) if passing else None
    out={"generated_at":datetime.now(timezone.utc).isoformat(),"mdd_floor_pct":-70,"rows":rows,"passing_count":len(passing),"best_passing":best}
    path=core.RESULT_DIR/"aggressive_stage14.json";path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"saved":str(path),"passing":len(passing),"best":best},ensure_ascii=False,indent=2))

if __name__=="__main__":main()

from __future__ import annotations

import json
from datetime import datetime, timezone
import numpy as np

import replay_mdd30 as core
import combine_novel_patterns as combo

SYMBOLS=("AVAX","ICP","BCH","DOGE","UNI")
BASE=np.array([3.,5.,3.,5.,2.])


def data():
    src=json.loads((core.RESULT_DIR/"novel_pattern_search_stage10.json").read_text(encoding="utf-8"))
    best={x["best"]["symbol"]:x["best"] for x in src["results"] if x["best"]}
    streams={s:combo.trade_stream(best[s]) for s in SYMBOLS}; times=sorted(set().union(*(set(v) for v in streams.values())))
    return np.array([[streams[s].get(t,0.) for s in SYMBOLS] for t in times],dtype=float)


def simulate(matrix,w,start,end,lookback,min_mean,dd1,dd2,cost_stress=1.):
    history=[[] for _ in SYMBOLS]; eq=peak=1.; mdd=0.; events=trades=wins=0
    for row in matrix[start:end]:
        active=row!=0
        if not active.any(): continue
        allowed=np.array([len(history[i])<lookback or np.mean(history[i][-lookback:])>=min_mean for i in range(len(SYMBOLS))])
        mask=active&allowed
        for i in np.flatnonzero(active): history[i].append(float(row[i]))
        if not mask.any(): continue
        dd=eq/peak-1; throttle=.35 if dd<=dd2 else .65 if dd<=dd1 else 1.
        extra=(cost_stress-1.)*.0015*BASE
        legs=(row-extra*active)*w*mask*throttle; net=float(legs.sum())
        eq*=max(0.,1+net);peak=max(peak,eq);mdd=min(mdd,eq/peak-1)
        adjusted = row - extra * active
        events+=1;trades+=int(mask.sum());wins+=int(((adjusted>0)&mask).sum())
        if eq<=0:break
    return {"multiple":eq,"return_pct":(eq-1)*100,"mdd_pct":mdd*100,"events":events,"trades":trades,"win_rate_pct":wins/trades*100 if trades else 0}


def main():
    matrix=data(); cuts=(0,len(matrix)//3,2*len(matrix)//3,len(matrix))
    prior=json.loads((core.RESULT_DIR/"novel_pattern_risk_optimization_stage12.json").read_text(encoding="utf-8"))
    weights=[np.array([x["weights"][s] for s in SYMBOLS]) for x in prior["top_200"][:80]]
    tested=[]
    for w in weights:
      for lookback in (5,10,20,40):
       for min_mean in (-.01,-.005,0.,.005):
        for dd1,dd2 in ((-.10,-.20),(-.15,-.25),(-.20,-.30)):
         seg=[simulate(matrix,w,cuts[k],cuts[k+1],lookback,min_mean,dd1,dd2) for k in range(3)]
         if not all(x["return_pct"]>0 and x["mdd_pct"]>=-50 and x["trades"]>=30 for x in seg):continue
         full=simulate(matrix,w,0,len(matrix),lookback,min_mean,dd1,dd2); stress=simulate(matrix,w,0,len(matrix),lookback,min_mean,dd1,dd2,2.)
         score=min(np.log(max(x["multiple"],1e-12)) for x in seg)+np.log(max(full["multiple"],1e-12))/4
         passed=full["return_pct"]>=1_000_000 and full["mdd_pct"]>=-50 and stress["mdd_pct"]>=-50 and stress["return_pct"]>0
         tested.append({"score":float(score),"weights":dict(zip(SYMBOLS,map(float,w))),"gross":float(w@BASE),"lookback":lookback,"min_prior_mean":min_mean,"drawdown_throttle":[dd1,dd2],"segments":seg,"full":full,"double_cost":stress,"passed":bool(passed)})
    tested.sort(key=lambda x:(x["passed"],x["score"]),reverse=True);passing=[x for x in tested if x["passed"]]
    out={"generated_at":datetime.now(timezone.utc).isoformat(),"tested":len(tested),"passing_count":len(passing),"best":tested[0],"passing":passing[:20],"top_100":tested[:100]}
    path=core.RESULT_DIR/"adaptive_filter_stage13.json";path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"saved":str(path),"tested":len(tested),"passing":len(passing),"best":tested[0]},ensure_ascii=False,indent=2))

if __name__=="__main__":main()

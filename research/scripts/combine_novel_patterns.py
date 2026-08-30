from __future__ import annotations

import itertools, json
from datetime import datetime, timezone

import numpy as np

import replay_mdd30 as core
import search_novel_patterns as novel


def matching_signal(rows, candidate):
    def normalized(value):
        if isinstance(value, tuple): return [normalized(x) for x in value]
        if isinstance(value, list): return [normalized(x) for x in value]
        if isinstance(value, dict): return {k: normalized(v) for k, v in value.items()}
        return value
    for family, params, sig in novel.signals(rows):
        if family == candidate["family"] and normalized(params) == normalized(candidate["params"]):
            return sig
    raise ValueError(f"signal not found: {candidate['symbol']}")


def trade_stream(candidate):
    rows = core.read_candles(core.DATA_DIR / f"{candidate['symbol']}USDT_1h.csv")
    sig = matching_signal(rows, candidate); hold = candidate["hold_hours"]; lev = candidate["leverage"]
    o = np.array([r["o"] for r in rows]); c = np.array([r["c"] for r in rows]); t = np.array([r["t"] for r in rows], dtype=np.int64)
    possible = np.flatnonzero(sig[169:len(rows)-hold-1]) + 169
    chosen=[]; next_allowed=-1
    for i in possible:
        if i >= next_allowed: chosen.append(int(i)); next_allowed=int(i)+hold+1
    idx=np.array(chosen,dtype=int); d=sig[idx]
    raw=d*(c[idx+1+hold]/o[idx+1]-1)*lev
    cost=(2*(novel.FEE_SIDE+novel.SLIPPAGE_SIDE)+hold/8*novel.FUNDING_8H)*lev
    return {int(ts):float(ret-cost) for ts,ret in zip(t[idx+1+hold],raw)}


def simulate(times, streams, symbols, scale, start, end):
    equity=peak=1.; mdd=0.; trades=wins=0; returns=[]
    weight=scale/len(symbols)
    for ts in times:
        if ts < start or ts >= end: continue
        active=[streams[s][ts] for s in symbols if ts in streams[s]]
        if not active: continue
        net=sum(active)*weight
        equity*=max(0.,1+net); peak=max(peak,equity); mdd=min(mdd,equity/peak-1)
        trades+=len(active); wins+=sum(x>0 for x in active); returns.extend(x*weight for x in active)
        if equity<=0: break
    return {"multiple":equity,"return_pct":(equity-1)*100,"mdd_pct":mdd*100,"trades":trades,
            "win_rate_pct":wins/trades*100 if trades else 0,"avg_trade_contribution_pct":np.mean(returns)*100 if returns else 0}


def main():
    source=json.loads((core.RESULT_DIR/"novel_pattern_search_stage10.json").read_text(encoding="utf-8"))
    candidates=sorted([x["best"] for x in source["results"] if x["best"] and x["best"]["transferable"]],key=lambda x:x["full"]["return_pct"],reverse=True)[:12]
    streams={x["symbol"]:trade_stream(x) for x in candidates}; times=sorted(set().union(*(set(x) for x in streams.values())))
    cuts=(times[0],times[len(times)//3],times[2*len(times)//3],times[-1]+1); tested=[]
    for size in (2,3,4,5,6):
        for combo in itertools.combinations(streams,size):
            for scale in (0.5,0.75,1.,1.25,1.5,2.,2.5,3.,3.5,4.):
                seg=[simulate(times,streams,combo,scale,cuts[k],cuts[k+1]) for k in range(3)]
                full=simulate(times,streams,combo,scale,cuts[0],cuts[-1])
                transferable=all(x["return_pct"]>0 and x["mdd_pct"]>=-50 and x["trades"]>=30 for x in seg)
                score=min(np.log(max(x["multiple"],1e-12)) for x in seg)+np.log(max(full["multiple"],1e-12))/4
                tested.append({"symbols":combo,"scale":scale,"segments":seg,"full":full,"transferable":transferable,"score":float(score)})
    tested.sort(key=lambda x:(x["transferable"],x["score"]),reverse=True)
    passing=[x for x in tested if x["transferable"] and x["full"]["return_pct"]>=1_000_000 and x["full"]["mdd_pct"]>=-50]
    out={"generated_at":datetime.now(timezone.utc).isoformat(),"candidate_symbols":[x["symbol"] for x in candidates],
         "tested":len(tested),"best":tested[0],"passing_1000000_count":len(passing),"passing":passing[:20],"top_50":tested[:50]}
    path=core.RESULT_DIR/"novel_pattern_portfolio_stage11.json"; path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"saved":str(path),"tested":len(tested),"passing":len(passing),"best":tested[0]},ensure_ascii=False,indent=2))


if __name__=="__main__": main()

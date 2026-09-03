"""Research only: combine frozen Stage32 LINK with new unused-symbol pattern families."""
import json
from datetime import datetime, timezone

import numpy as np

import research_b_idle_stage32 as p

s = p.s
OUT = s.core.RESULT_DIR / "b_idle_stage33"


def shifted_roll_mean(x, n):
    out = np.full(len(x), np.nan)
    if len(x) > n:
        out[n:] = np.convolve(x, np.ones(n)/n, "valid")[:-1]
    return out


def shifted_roll_std(x, n):
    m = shifted_roll_mean(x, n)
    q = shifted_roll_mean(x*x, n)
    return np.sqrt(np.maximum(0, q-m*m))


def new_patterns(rows):
    o,h,l,c,v = [np.array([r[k] for r in rows], dtype=float) for k in ("o","h","l","c","v")]
    span = np.maximum(h-l, 1e-12)
    lower=(np.minimum(o,c)-l)/span; upper=(h-np.maximum(o,c))/span
    body=(c-o)/span
    ret=np.r_[0.,c[1:]/c[:-1]-1]
    vol48=shifted_roll_mean(v,48)
    # Prior-window simple RSI, current completed candle supplies confirmation.
    gain=np.maximum(ret,0); loss=np.maximum(-ret,0)
    for n in (12,24,48):
        g=shifted_roll_mean(gain,n); d=shifted_roll_mean(loss,n)
        rsi=100*g/np.maximum(g+d,1e-12)
        for edge in (15,20,25):
            sig=np.where((rsi<edge)&(body>.2)&(lower>.25),1,np.where((rsi>100-edge)&(body<-.2)&(upper>.25),-1,0))
            yield f"rsi_reversal_n{n}_e{edge}",sig
    # Price stretch outside the prior distribution, then candle rejection.
    for n in (24,72,168):
        mean=shifted_roll_mean(c,n); sd=shifted_roll_std(c,n)
        z=(c-mean)/np.maximum(sd,1e-12)
        for edge in (2.,2.5,3.):
            sig=np.where((z < -edge)&(lower>.45)&(c>o),1,np.where((z>edge)&(upper>.45)&(c<o),-1,0))
            yield f"z_reject_n{n}_e{edge}",sig
    # Abnormal volume impulse that fails inside the same completed candle.
    for vr in (1.5,2.,3.):
        for move in (.015,.025,.04):
            sig=np.where((ret < -move)&(v>vol48*vr)&(lower>.5)&(c>o),1,np.where((ret>move)&(v>vol48*vr)&(upper>.5)&(c<o),-1,0))
            yield f"volume_failure_v{vr}_m{move}",sig
    # Quiet prior volatility followed by a failed range break, not trend following.
    fast=shifted_roll_std(ret,12); slow=shifted_roll_std(ret,72)
    for ratio in (.4,.55,.7):
        for move in (.01,.02):
            sig=np.where((fast<slow*ratio)&(ret < -move)&(lower>.5),1,np.where((fast<slow*ratio)&(ret>move)&(upper>.5),-1,0))
            yield f"quiet_failed_break_r{ratio}_m{move}",sig


def main():
    OUT.mkdir(exist_ok=True)
    series, entries, times, standard = p.current_stage26()
    run = p.weighted_replay()
    base = run(series,entries,times,1.15)
    assert abs(base["return_pct"]-standard["reference"]["return_pct"])<1e-6
    base_stress=run(series,entries,times,1.15,cost_mult=2)
    busy=set()
    for t,ps in entries.items():
        for x in ps:busy.update(range(t,x["exit_bar"]+3600000,3600000))
    cuts=[times[0]+int((times[-1]+3600000-times[0])*k/3) for k in range(4)]
    # Stage32 LINK rule is fixed before this search.
    link_rows=s.core.read_candles(s.core.DATA_DIR/"LINKUSDT_1h.csv")
    for r in link_rows:r["symbol"]="LINK"
    link_sig=dict(p.candidate_patterns(link_rows))["exhaust_n3_move0.05"]
    link_ops=s.opportunities(link_rows,link_sig,1,3,busy)
    series["LINK"]={r["t"]:r for r in link_rows}
    excluded=p.CURRENT_B|p.PLAN_A|{"LINK"}
    rowsets={}; candidates=[]
    for path in sorted(s.core.DATA_DIR.glob("*USDT_1h.csv")):
        symbol=path.name.replace("USDT_1h.csv","")
        if symbol in excluded:continue
        rows=s.core.read_candles(path)
        if rows[0]["t"]>times[0] or rows[-1]["t"]<times[-1]:continue
        for r in rows:r["symbol"]=symbol
        rowsets[symbol]=rows
        prefix=dict(new_patterns(rows[:1200]))
        for name,sig in new_patterns(rows):
            np.testing.assert_array_equal(sig[:1200],prefix[name])
            for lev in (2,3):
                ops=s.opportunities(rows,sig,1,lev,busy)
                seg=s.screen(rows,ops,cuts)
                if all(z["trades"]>=8 and z["sum_log"]>0 for z in seg):
                    candidates.append(dict(id=f"{symbol}:{name}:l{lev}",symbol=symbol,pattern=name,leverage=lev,ops=ops,segments=seg,score=min(z["sum_log"] for z in seg)))
        print("SCREEN",symbol,len(candidates),flush=True)
    ranked=sorted(candidates,key=lambda x:(x["score"],sum(z["sum_log"] for z in x["segments"])),reverse=True)
    selected=[]
    for x in ranked:
        if x["symbol"] not in {z["symbol"] for z in selected}:selected.append(x)
        if len(selected)>=16:break
    results=[]
    for x in selected:
        ss={**series,x["symbol"]:{r["t"]:r for r in rowsets[x["symbol"]]}}
        for link_frac,other_frac in ((.25,.15),(.2,.2),(.15,.25)):
            ee={t:[dict(q) for q in ps] for t,ps in entries.items()}
            for op in link_ops:ee.setdefault(op["entry_ts"],[]).append({**op,"weight_scale":link_frac/1.15})
            for op in x["ops"]:ee.setdefault(op["entry_ts"],[]).append({**op,"weight_scale":other_frac/1.15})
            full=run(ss,ee,times,1.15);stress=run(ss,ee,times,1.15,cost_mult=2)
            segs=[p.compact(run(ss,ee,times,1.15,start=cuts[k],end=cuts[k+1])) for k in range(3)]
            extras=[q for q in full["ledger"] if q["symbol"] in {"LINK",x["symbol"]}]
            base_rows=[q for q in full["ledger"] if q["symbol"] in p.CURRENT_B]
            overlap=sum(any(q["entry_ts"]<z["exit_ts"] and q["exit_ts"]>z["entry_ts"] for z in base_rows) for q in extras)
            assert overlap==0
            passed=full["return_pct"]>base["return_pct"] and stress["return_pct"]>base_stress["return_pct"] and full["hourly_mark_mdd_pct"]>=-70 and not full["liquidation_proxy_count"] and not stress["liquidation_proxy_count"] and all(z["return_pct"]>0 for z in segs)
            results.append(dict(candidate={k:v for k,v in x.items() if k!="ops"},link_fraction=link_frac,candidate_fraction=other_frac,total_fraction=.4,full=p.compact(full),double_cost=p.compact(stress),segments=segs,extra_trades=len(extras),holding_overlap_trades=overlap,passed=passed))
    results.sort(key=lambda x:(x["passed"],x["full"]["return_pct"]),reverse=True)
    output=dict(id="B-IDLE-STAGE33",generated_at=datetime.now(timezone.utc).isoformat(),research_only=True,baseline=p.compact(base),baseline_double_cost=p.compact(base_stress),fixed_link=dict(pattern="LINK exhaust_n3_move0.05",leverage=3,hold_hours=1),tested_candidates=len(candidates),selected_candidates=len(selected),results=results,limitations=["All thirds used for comparison; not independent holdout","Binance spot OHLC proxy, not BingX futures fills","Research only; no A or live B changes"])
    (OUT/"results.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({"tested":len(candidates),"passes":sum(x["passed"] for x in results),"best":results[0] if results else None},ensure_ascii=False),flush=True)


if __name__=="__main__":main()

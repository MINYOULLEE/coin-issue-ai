from __future__ import annotations

import json
from datetime import datetime, timezone
import numpy as np

import replay_mdd30 as core
import combine_novel_patterns as combo
import search_novel_patterns as novel

SYMBOLS=("AVAX","ICP","BCH","DOGE","UNI")

def audit(candidate):
    symbol=candidate["symbol"]; rows=core.read_candles(core.DATA_DIR/f"{symbol}USDT_1h.csv")
    sig=combo.matching_signal(rows,candidate);hold=int(candidate["hold_hours"]);lev=float(candidate["leverage"])
    o=np.array([r["o"] for r in rows]);h=np.array([r["h"] for r in rows]);l=np.array([r["l"] for r in rows]);c=np.array([r["c"] for r in rows]);t=np.array([r["t"] for r in rows],dtype=np.int64)
    possible=np.flatnonzero(sig[169:len(rows)-hold-1])+169; chosen=[]; nxt=-1
    for i in possible:
        if i>=nxt:chosen.append(int(i));nxt=int(i)+hold+1
    trades=[]; breaches=0; safety_breaches=0; worst_mae=0.; worst_lev_mae=0.
    # Approximate isolated liquidation: 100%/leverage adverse move. 90% of that
    # is also reported as a maintenance-margin safety boundary.
    for i in chosen:
        d=float(sig[i]);entry=float(o[i+1]);exit_price=float(c[i+1+hold])
        adverse=(float(np.min(l[i+1:i+2+hold]))/entry-1) if d>0 else (entry/float(np.max(h[i+1:i+2+hold]))-1)
        lev_mae=adverse*lev; breached=lev_mae<=-1.; safety=lev_mae<=-.9
        breaches+=breached;safety_breaches+=safety;worst_mae=min(worst_mae,adverse);worst_lev_mae=min(worst_lev_mae,lev_mae)
        if breached or safety:
            trades.append({"signal_time":int(t[i]),"entry_time":int(t[i+1]),"side":"long" if d>0 else "short","entry":entry,"exit":exit_price,"mae_pct":adverse*100,"leveraged_mae_pct":lev_mae*100,"liquidation_proxy":bool(breached),"safety_boundary":bool(safety)})
    return {"symbol":symbol,"leverage":lev,"hold_hours":hold,"trades":len(chosen),"liquidation_proxy_breaches":int(breaches),"safety_boundary_breaches":int(safety_breaches),"worst_intratrade_mae_pct":worst_mae*100,"worst_leveraged_mae_pct":worst_lev_mae*100,"breach_examples":trades[:20]}

def main():
    src=json.loads((core.RESULT_DIR/"novel_pattern_search_stage10.json").read_text(encoding="utf-8")); best={x["best"]["symbol"]:x["best"] for x in src["results"] if x["best"]}
    audits=[audit(best[s]) for s in SYMBOLS];total=sum(x["trades"] for x in audits);breaches=sum(x["liquidation_proxy_breaches"] for x in audits);safety=sum(x["safety_boundary_breaches"] for x in audits)
    out={"generated_at":datetime.now(timezone.utc).isoformat(),"basis":"hourly high/low path; isolated-margin approximation before maintenance margin and fees","total_trades":total,"liquidation_proxy_breaches":breaches,"safety_boundary_breaches":safety,"passed":breaches==0 and safety==0,"symbols":audits}
    path=core.RESULT_DIR/"aggressive_liquidation_audit_stage15.json";path.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=="__main__":main()

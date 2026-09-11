"""Public perpetual-minute execution check for the frozen Stage64 candidate.

No credentials and no orders.  The selected 26 changed spot opportunities are
replayed on Binance USD-M perpetual 1-minute bars with delayed market fills.
"""
import hashlib, json, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import numpy as np
import research_dynamic_targets_stage58 as s58
import research_profit_lock_stage61 as s61

M=60_000; H=s58.H
OUT=s58.OUT.parent/"profit_lock_fills_stage65"; CACHE=OUT/"binance_futures_minutes"
CHOICES={"ICP":(.30,.70),"BCH":(.70,.75),"UNI":(.60,.75)}

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"coin-issue-research/1.0"})
    with urllib.request.urlopen(req,timeout=30) as response:return json.load(response)

def fetch(job):
    symbol,t,end=job; path=CACHE/f"{symbol}_{t}.json"
    if path.exists(): raw=json.loads(path.read_text(encoding="utf8"))
    else:
        query=urllib.parse.urlencode({"symbol":symbol+"USDT","interval":"1m","startTime":t,"endTime":end-1,"limit":1000})
        raw=get("https://fapi.binance.com/fapi/v1/klines?"+query);path.write_text(json.dumps(raw),encoding="utf8")
    if not isinstance(raw,list):raise ValueError(str(raw)[:200])
    rows={int(x[0]):{"o":float(x[1]),"h":float(x[2]),"l":float(x[3]),"c":float(x[4])} for x in raw}
    expected=list(range(t,end,M))
    if sorted(rows)!=expected:raise ValueError(f"minute gap {symbol} {t}: {len(rows)}/{len(expected)}")
    return (symbol,t),rows

def execute(rows,p,decision,keep,entry_delay,exit_delay,haircut):
    t=p["entry_ts"];end=p["exit_bar"]+H;side=p["side"]
    entry=rows[t+entry_delay*M]["o"]*(1+side*.0002)
    trigger_pct=decision["trigger_distance"]/decision["raw_entry"]
    armed=False;stop=None;peak=0.;fill=None;trigger_minute=None
    for hour in range(t,end,H):
        if armed:
            stamps=range(hour+entry_delay*M if hour==t else hour,hour+H,M)
            for stamp in stamps:
                bar=rows[stamp];touched=bar["l"]<=stop if side>0 else bar["h"]>=stop
                if touched:
                    trigger_minute=stamp;fill_stamp=min(stamp+exit_delay*M,end-M)
                    # Delayed market order uses the next available minute open;
                    # an extra adverse haircut covers trigger/market slippage.
                    raw=stop if exit_delay==0 else rows[fill_stamp]["o"]
                    fill=raw*(1-side*haircut);break
            if fill is not None:break
        close=rows[hour+H-M]["c"]
        favorable=side*(close-entry)/entry;peak=max(peak,favorable)
        if peak>=trigger_pct:
            armed=True;candidate=entry*(1+side*peak*keep)
            stop=max(stop,candidate) if side>0 and stop is not None else min(stop,candidate) if side<0 and stop is not None else candidate
    baseline=rows[end-M]["c"]*(1-side*.0002)
    actual=fill if fill is not None else baseline
    # Round-trip fee plus the entry/exit slippage already embedded in prices.
    base_net=side*(baseline-entry)/entry-.001
    cand_net=side*(actual-entry)/entry-.001
    return {"armed":armed,"protected_exit":fill is not None,"trigger_minute":trigger_minute,"fill_price":fill,
            "baseline_margin_return_pct":base_net*p["lev"]*100,
            "candidate_margin_return_pct":cand_net*p["lev"]*100,
            "improvement_pp":(cand_net-base_net)*p["lev"]*100}

def main():
    OUT.mkdir(exist_ok=True);CACHE.mkdir(exist_ok=True)
    series,core,times,std,op=s58.current.s40.build();weights={s:float(std["symbols"][s]["target_margin_fraction"]) for s in op}
    entries=s58.current.s40.entries_for(core,op,weights);ps={(p["symbol"],t):p for t,xs in entries.items() for p in xs}
    features={s:s58.old.prev.features(list(v.values())) for s,v in series.items()}
    selected=[]
    for symbol,(q,keep) in CHOICES.items():
        exits,decisions=s61.learned_profit_locks(series,entries,features,symbol.lower(),q,keep)
        by_key={(d["symbol"],d["entry_ts"]):d for d in decisions}
        for key in sorted({(s,t) for s,t,_ in exits}):
            p=ps[key];d=by_key[key];selected.append({"key":key,"p":p,"decision":{**d,"raw_entry":series[key[0]][key[1]]["o"]},"keep":keep})
    windows={};errors=[]
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs={pool.submit(fetch,(x["key"][0],x["p"]["entry_ts"],x["p"]["exit_bar"]+H)):x for x in selected}
        for future in as_completed(jobs):
            x=jobs[future]
            try:key,rows=future.result();windows[key]=rows
            except Exception as exc:errors.append({"symbol":x["key"][0],"entry_ts":x["key"][1],"error":str(exc)})
    diagnostics=[]
    for x in selected:
        if x["key"] not in windows:continue
        for entry_delay in (0,1,3,5):
            for exit_delay in (0,1,3,5):
                for haircut in (0,.0005,.001):
                    diagnostics.append({"symbol":x["key"][0],"entry_ts":x["key"][1],"entry_delay":entry_delay,
                      "exit_delay":exit_delay,"haircut":haircut,**execute(windows[x["key"]],x["p"],x["decision"],x["keep"],entry_delay,exit_delay,haircut)})
    summaries=[]
    for entry_delay in (0,1,3,5):
        for exit_delay in (0,1,3,5):
            for haircut in (0,.0005,.001):
                xs=[x for x in diagnostics if x["entry_delay"]==entry_delay and x["exit_delay"]==exit_delay and x["haircut"]==haircut]
                summaries.append({"entry_delay":entry_delay,"exit_delay":exit_delay,"haircut":haircut,"windows":len(xs),
                  "armed":sum(x["armed"] for x in xs),"protected_exits":sum(x["protected_exit"] for x in xs),
                  "improved":sum(x["improvement_pp"]>1e-9 for x in xs),"worsened":sum(x["improvement_pp"]<-1e-9 for x in xs),
                  "mean_improvement_pp":float(np.mean([x["improvement_pp"] for x in xs])) if xs else None,
                  "median_improvement_pp":float(np.median([x["improvement_pp"] for x in xs])) if xs else None,
                  "total_improvement_pp":float(sum(x["improvement_pp"] for x in xs))})
    output={"id":"B-PROFIT-LOCK-FILLS-STAGE65","generated_at":datetime.now(timezone.utc).isoformat(),
      "research_only":True,"orders_submitted":0,"requested_windows":len(selected),"complete_windows":len(windows),"errors":errors,
      "source":"Binance USD-M perpetual public 1-minute trades; not BingX fills","choices":CHOICES,
      "summaries":summaries,"diagnostics":diagnostics,
      "limitations":["Selection-biased 26 spot-changed opportunities, not every opportunity","No actual BingX order placed",
        "No tick order book or mark-price trigger history","Portfolio compounding/MDD remains the Stage64 spot replay"],
      "hashes":{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in CACHE.glob("*.json")}}
    (OUT/"RESULTS.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({k:v for k,v in output.items() if k not in ("diagnostics","hashes")},ensure_ascii=False),flush=True)

if __name__=="__main__":main()

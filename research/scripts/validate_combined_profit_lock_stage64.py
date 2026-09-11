"""Combine the independently robust Stage63 symbol-level profit locks."""
import itertools, json
from datetime import datetime, timezone

import research_dynamic_targets_stage58 as s58
import research_profit_lock_stage61 as s61

OUT=s58.OUT.parent/"combined_profit_lock_stage64"
CHOICES={
    "ICP": (.30,.70,False),
    "BCH": (.70,.75,False),
    "UNI": (.60,.75,False),
}

def compact(x): return {k:v for k,v in x.items() if k!="ledger"}

def main():
    OUT.mkdir(exist_ok=True)
    series,core,times,std,op=s58.current.s40.build()
    weights={s:float(std["symbols"][s]["target_margin_fraction"]) for s in op}
    entries=s58.current.s40.entries_for(core,op,weights)
    features={s:s58.old.prev.features(list(v.values())) for s,v in series.items()}
    cuts=[times[0]+int((times[-1]+s58.H-times[0])*k/3) for k in range(4)]
    cache={}
    for symbol,(q,keep,conditional) in CHOICES.items():
        cache[symbol]=s61.learned_profit_locks(series,entries,features,symbol.lower(),q,keep,conditional)[0]
    results=[]
    for size in range(0,len(CHOICES)+1):
        for symbols in itertools.combinations(CHOICES,size):
            exits={}
            for symbol in symbols: exits.update(cache[symbol])
            replay=s58.old.runner(exits);run=lambda **kw:replay(series,entries,times,1.15,**kw)
            results.append({"symbols":list(symbols),"full":compact(run()),"double_cost":compact(run(cost_mult=2)),
                "segments":[compact(run(start=cuts[k],end=cuts[k+1])) for k in range(3)],"changed_exits":len(exits)})
    base=results[0]
    for x in results:
        x["strict_pass"]=bool(x["symbols"] and x["full"]["return_pct"]>base["full"]["return_pct"]
          and x["double_cost"]["return_pct"]>base["double_cost"]["return_pct"]
          and x["full"]["hourly_mark_mdd_pct"]>=base["full"]["hourly_mark_mdd_pct"]
          and all(x["segments"][k]["return_pct"]>=base["segments"][k]["return_pct"] for k in range(3)))
    output={"id":"B-COMBINED-PROFIT-LOCK-STAGE64","generated_at":datetime.now(timezone.utc).isoformat(),
      "research_only":True,"runtime_id":std["strategy_id"],"start_usd":100,"choices":CHOICES,"results":results,
      "limitations":["Binance spot hourly proxy","Components and combination selected on previously researched data","No independent holdout","No live changes"]}
    (OUT/"RESULTS.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps(sorted(results,key=lambda x:x["full"]["return_pct"],reverse=True),ensure_ascii=False),flush=True)

if __name__=="__main__":main()

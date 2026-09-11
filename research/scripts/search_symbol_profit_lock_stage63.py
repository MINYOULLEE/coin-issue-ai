"""Broad per-symbol causal profit-lock search with strict cross-period screening."""
import json
from datetime import datetime, timezone

import research_dynamic_targets_stage58 as s58
import research_profit_lock_stage61 as s61

OUT = s58.OUT.parent / "symbol_profit_lock_stage63"
SYMBOLS = ("AVAX", "ICP", "BCH", "DOGE", "UNI")
QUANTILES = (.30, .40, .50, .60, .70, .80)
KEEPS = (.50, .60, .70, .75, .80, .90)


def compact(result):
    return {k: v for k, v in result.items() if k != "ledger"}


def main():
    OUT.mkdir(exist_ok=True)
    series, core_entries, times, standard, opportunities = s58.current.s40.build()
    weights = {symbol: float(standard["symbols"][symbol]["target_margin_fraction"]) for symbol in opportunities}
    entries = s58.current.s40.entries_for(core_entries, opportunities, weights)
    features = {symbol: s58.old.prev.features(list(rows.values())) for symbol, rows in series.items()}
    cuts = [times[0] + int((times[-1] + s58.H - times[0]) * k / 3) for k in range(4)]
    base_replay = s58.old.runner({})
    base_run = lambda **kw: base_replay(series, entries, times, 1.15, **kw)
    base = {"full": compact(base_run()), "double_cost": compact(base_run(cost_mult=2)),
            "segments": [compact(base_run(start=cuts[k], end=cuts[k + 1])) for k in range(3)]}

    # First pass ranks the broad grid on the full period. Only the leading
    # candidates receive the more expensive segment and cost-stress replay.
    broad = []
    exit_cache = {}
    for symbol in SYMBOLS:
        for conditional in (False, True):
            for q in QUANTILES:
                for keep in KEEPS:
                    key = (symbol, conditional, q, keep)
                    exits, decisions = s61.learned_profit_locks(series, entries, features, symbol.lower(), q, keep, conditional)
                    exit_cache[key] = exits
                    replay = s58.old.runner(exits)
                    result = compact(replay(series, entries, times, 1.15))
                    broad.append({"symbol":symbol,"conditional":conditional,"q":q,"keep":keep,
                                  "full":result,"armed":sum(bool(x.get("armed")) for x in decisions),"exits":len(exits)})
        print("searched", symbol, flush=True)

    finalists = []
    for symbol in SYMBOLS:
        pool = [x for x in broad if x["symbol"] == symbol]
        # Evaluate top ten plus every candidate that beats baseline full-period return.
        selected = sorted(pool, key=lambda x:x["full"]["return_pct"], reverse=True)[:10]
        selected += [x for x in pool if x["full"]["return_pct"] > base["full"]["return_pct"] and x not in selected]
        for item in selected:
            key=(item["symbol"],item["conditional"],item["q"],item["keep"])
            replay=s58.old.runner(exit_cache[key]); run=lambda **kw:replay(series,entries,times,1.15,**kw)
            item["double_cost"]=compact(run(cost_mult=2))
            item["segments"]=[compact(run(start=cuts[k],end=cuts[k+1])) for k in range(3)]
            item["strict_pass"]=(item["full"]["return_pct"]>base["full"]["return_pct"]
                and item["double_cost"]["return_pct"]>base["double_cost"]["return_pct"]
                and item["full"]["hourly_mark_mdd_pct"]>=base["full"]["hourly_mark_mdd_pct"]
                and all(item["segments"][k]["return_pct"]>=base["segments"][k]["return_pct"] for k in range(3)))
            finalists.append(item)
        print("validated", symbol, len(selected), flush=True)

    passing=sorted([x for x in finalists if x["strict_pass"]],key=lambda x:x["full"]["return_pct"],reverse=True)
    output={"id":"B-SYMBOL-PROFIT-LOCK-STAGE63","generated_at":datetime.now(timezone.utc).isoformat(),
            "research_only":True,"runtime_id":standard["strategy_id"],"start_usd":100,
            "tested":len(broad),"base":base,"finalists":finalists,"passing":passing,
            "definition":"Per core symbol, compare causal prior-winner MFE/ATR activation, optional direction/efficiency regime match, and next-candle 50-90% peak-close profit retention.",
            "limitations":["Binance spot hourly proxy","Grid searched on previously researched data","No independent holdout","No live changes"]}
    (OUT/"RESULTS.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({"tested":len(broad),"passed":len(passing),"top":passing[:10]},ensure_ascii=False),flush=True)


if __name__=="__main__":
    main()

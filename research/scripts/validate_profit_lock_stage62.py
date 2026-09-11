"""Neighbourhood stability check for the Stage61 UNI profit-lock candidate."""
import json
from datetime import datetime, timezone

import research_dynamic_targets_stage58 as s58
import research_profit_lock_stage61 as s61

OUT = s58.OUT.parent / "profit_lock_stage62"
QUANTILES = (.55, .60, .65, .70, .75)
KEEP = (.65, .70, .75, .80, .85)


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
    results = []
    for q in QUANTILES:
        for keep in KEEP:
            exits, decisions = s61.learned_profit_locks(series, entries, features, "uni", q, keep)
            replay = s58.old.runner(exits)
            run = lambda **kw: replay(series, entries, times, 1.15, **kw)
            item = {"q": q, "keep": keep, "full": compact(run()), "double_cost": compact(run(cost_mult=2)),
                    "segments": [compact(run(start=cuts[k], end=cuts[k + 1])) for k in range(3)],
                    "armed": sum(bool(x.get("armed")) for x in decisions), "exits": len(exits)}
            item["strict_pass"] = (item["full"]["return_pct"] > base["full"]["return_pct"]
                and item["double_cost"]["return_pct"] > base["double_cost"]["return_pct"]
                and item["full"]["hourly_mark_mdd_pct"] >= base["full"]["hourly_mark_mdd_pct"]
                and all(item["segments"][i]["return_pct"] >= base["segments"][i]["return_pct"] for i in range(3)))
            results.append(item)
            print(q, keep, item["full"]["return_pct"], item["strict_pass"], flush=True)
    output = {"id":"B-UNI-PROFIT-LOCK-STAGE62","generated_at":datetime.now(timezone.utc).isoformat(),
              "research_only":True,"runtime_id":standard["strategy_id"],"start_usd":100,
              "baseline":base,"results":results,
              "limitations":["Binance spot hourly proxy","Previously researched data, not independent holdout","No live changes"]}
    (OUT/"RESULTS.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf8")
    passing=[x for x in results if x["strict_pass"]]
    print(json.dumps({"tested":len(results),"passed":len(passing),"best":max(results,key=lambda x:x["full"]["return_pct"])},ensure_ascii=False),flush=True)


if __name__ == "__main__":
    main()

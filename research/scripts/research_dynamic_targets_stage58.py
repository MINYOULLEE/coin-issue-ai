"""Research-only causal dynamic profit targets for the current B Stage45 portfolio."""
import hashlib, json
from datetime import datetime, timezone

import research_conditional_exits_stage28 as old
import verify_b_combo_stage44 as current

H = 3_600_000
OUT = old.prev.a.RESULT_DIR / "dynamic_targets_stage58"
RULES = [
    ("baseline", None, None, False, False),
    ("target_q30", None, .30, False, False),
    ("target_q50", None, .50, False, False),
    ("target_q65", None, .65, False, False),
    ("target_q80", None, .80, False, False),
    ("target_q95", None, .95, False, False),
    ("picture_q50", None, .50, True, False),
    ("picture_q65", None, .65, True, False),
    ("picture_q80", None, .80, True, False),
]

def compact(result):
    return {k: v for k, v in result.items() if k != "ledger"}

def main():
    OUT.mkdir(exist_ok=True)
    series, core_entries, times, standard, opportunities = current.s40.build()
    weights = {symbol: float(standard["symbols"][symbol]["target_margin_fraction"]) for symbol in opportunities}
    entries = current.s40.entries_for(core_entries, opportunities, weights)
    features = {symbol: old.prev.features(list(rows.values())) for symbol, rows in series.items()}
    cuts = [times[0] + int((times[-1] + H - times[0]) * k / 3) for k in range(4)]
    results = []
    for rule in RULES:
        exits, decisions = old.learned_exits(series, entries, features, rule)
        replay = old.runner(exits)
        run = lambda **kw: replay(series, entries, times, 1.15, **kw)
        full, stress = run(), run(cost_mult=2)
        segments = [compact(run(start=cuts[k], end=cuts[k+1])) for k in range(3)]
        results.append({
            "rule": rule[0], "full": compact(full), "double_cost": compact(stress), "segments": segments,
            "targets_armed": sum(d["active"] for d in decisions), "targets_hit": len(exits),
            "target_hit_rate_pct": 100 * len(exits) / max(1, sum(d["active"] for d in decisions)),
            "ambiguous_hours": sum(bool(d.get("ambiguous")) for d in decisions),
        })
        (OUT / f"{rule[0]}.json").write_text(json.dumps({"summary": results[-1], "ledger": full["ledger"], "decisions": decisions}, ensure_ascii=False, indent=2), encoding="utf8")
        print(rule[0], json.dumps(results[-1]["full"]), flush=True)
    baseline = results[0]
    for item in results:
        item["pass"] = (item["rule"] != "baseline" and item["full"]["return_pct"] > baseline["full"]["return_pct"]
            and item["double_cost"]["return_pct"] > baseline["double_cost"]["return_pct"]
            and item["full"]["hourly_mark_mdd_pct"] >= -70
            and item["full"]["liquidation_proxy_count"] == 0
            and item["double_cost"]["liquidation_proxy_count"] == 0
            and all(x["return_pct"] > 0 for x in item["segments"]))
    nominations=[]
    for k in range(3):
        winner=max(results,key=lambda x:x["segments"][k]["return_pct"])
        nominations.append({"discovery_third":k+1,"winner":winner["rule"],"cross_returns":[x["return_pct"] for x in winner["segments"]]})
    output={"id":"B-DYNAMIC-TARGETS-STAGE58","generated_at":datetime.now(timezone.utc).isoformat(),
        "research_only":True,"runtime_id":standard["strategy_id"],"start_usd":100,"results":results,"nominations":nominations,
        "target_definition":"At entry, target distance is a quantile of MFE/ATR from up to 120 prior completed profitable opportunities of the same symbol and side, multiplied by current pre-entry ATR. picture rules first use matching direction/regime when >=12 winners.",
        "causality":"Only opportunities whose original scheduled exit was already known are eligible training data.",
        "data_sha256":{s:hashlib.sha256((old.prev.a.DATA_DIR/f"{s}USDT_1h.csv").read_bytes()).hexdigest() for s in series},
        "limitations":["All thirds previously exposed to strategy research; not independent holdout","Binance spot hourly proxy, not BingX futures fills","Same-hour target touch assumes target fill; stop is not added","No live changes"]}
    (OUT/"RESULTS.json").write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding="utf8")
    print(json.dumps({"baseline":baseline,"best":max(results,key=lambda x:x["full"]["return_pct"]),"nominations":nominations},ensure_ascii=False),flush=True)

if __name__ == "__main__": main()

"""Research-only: apply causal dynamic targets only to B Stage45 UNI session trades."""
import json
from datetime import datetime, timezone

import research_dynamic_targets_stage58 as s58

OUT = s58.OUT.parent / "uni_targets_stage60"
RULES = [
    ("baseline", None, None, False, False),
    ("uni_q30", None, .30, False, False),
    ("uni_q50", None, .50, False, False),
    ("uni_q65", None, .65, False, False),
    ("uni_q80", None, .80, False, False),
    ("uni_q95", None, .95, False, False),
]


def compact(result):
    return {k: v for k, v in result.items() if k != "ledger"}


def main():
    OUT.mkdir(exist_ok=True)
    series, core_entries, times, standard, opportunities = s58.current.s40.build()
    weights = {symbol: float(standard["symbols"][symbol]["target_margin_fraction"]) for symbol in opportunities}
    entries = s58.current.s40.entries_for(core_entries, opportunities, weights)
    features = {symbol: s58.old.prev.features(list(rows.values())) for symbol, rows in series.items()}
    cuts = [times[0] + int((times[-1] + s58.H - times[0]) * k / 3) for k in range(4)]
    results = []
    for rule in RULES:
        learned_rule = (rule[0], rule[1], rule[2], rule[3], rule[4])
        exits, decisions = s58.old.learned_exits(series, entries, features, learned_rule)
        if rule[0] != "baseline":
            exits = {key: value for key, value in exits.items() if key[0] == "UNI"}
        replay = s58.old.runner(exits)
        run = lambda **kw: replay(series, entries, times, 1.15, **kw)
        full, stress = run(), run(cost_mult=2)
        segments = [compact(run(start=cuts[k], end=cuts[k + 1])) for k in range(3)]
        uni_decisions = [d for d in decisions if d["symbol"] == "UNI"]
        item = {
            "rule": rule[0], "full": compact(full), "double_cost": compact(stress), "segments": segments,
            "targets_armed": sum(bool(d["active"]) for d in uni_decisions),
            "targets_hit": sum(1 for key in exits if key[0] == "UNI"),
        }
        results.append(item)
        print(rule[0], json.dumps(item["full"]), flush=True)
    base = results[0]
    for item in results:
        item["robust_pass"] = bool(
            item["rule"] != "baseline"
            and item["full"]["return_pct"] > base["full"]["return_pct"]
            and item["double_cost"]["return_pct"] > base["double_cost"]["return_pct"]
            and item["full"]["hourly_mark_mdd_pct"] >= base["full"]["hourly_mark_mdd_pct"]
            and all(item["segments"][i]["return_pct"] >= base["segments"][i]["return_pct"] for i in range(3))
        )
    output = {
        "id": "B-UNI-DYNAMIC-TARGETS-STAGE60",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "runtime_id": standard["strategy_id"],
        "start_usd": 100,
        "results": results,
        "definition": "Only UNI session trades receive a target derived causally from the selected quantile of prior completed profitable UNI same-side MFE/ATR, multiplied by current pre-entry ATR. All other B trades keep their original time exits.",
        "limitations": ["Binance spot hourly proxy", "No independent holdout", "Same-hour target touch assumes fill", "No live changes"],
    }
    (OUT / "RESULTS.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"best": max(results, key=lambda x: x["full"]["return_pct"]), "robust": [x["rule"] for x in results if x["robust_pass"]]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

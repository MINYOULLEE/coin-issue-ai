"""Refine the Stage114 SOL-short guard without using dates or future data."""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone

import evaluate_ab_7y as ab
import research_a_drawdown_guard_stage75 as a75
import research_ab_reinforcement_stage113 as s113
import validate_a_exposure_scale_stage68 as a68

OUT = ab.OUT / "A_STAGE115_SOL_SHORT_REFINEMENT.json"
H = ab.H
END = int(datetime(2026, 8, 30, tzinfo=timezone.utc).timestamp() * 1000)


def compact(x):
    return {k: v for k, v in x.items() if k not in ("stop_events", "ledger")}


def filtered(source, bars, btc_min, sol_min, breadth_min, multiplier):
    result = copy.deepcopy(source)
    for stamp, value in list(result["SOL"].items()):
        if value >= 0:
            continue
        now = stamp-H
        prior = stamp-169*H
        if now not in bars["BTC"] or prior not in bars["BTC"] or now not in bars["SOL"] or prior not in bars["SOL"]:
            continue
        btc_ret = bars["BTC"][now]["c"] / bars["BTC"][prior]["c"] - 1
        sol_ret = bars["SOL"][now]["c"] / bars["SOL"][prior]["c"] - 1
        breadth = sum(now in bars[s] and prior in bars[s] and bars[s][now]["c"] > bars[s][prior]["c"] for s in a68.SYMBOLS)
        if btc_ret >= btc_min and sol_ret >= sol_min and breadth >= breadth_min:
            result["SOL"][stamp] = value * multiplier
    return result


def main():
    maps, bars, funding = s113.a_inputs()
    start = min(set.intersection(*(set(bars[s]) for s in a68.SYMBOLS)))
    cfg = {"id": "guard35_075", "scale": 1.4, "dd_trigger": .35,
           "dd_reduced_scale": .75, "dd_recovery": .175}
    baseline = {
        "early": a75.run(maps, bars, funding, cfg, start=start, end=s113.CUT),
        "five": a75.run(maps, bars, funding, cfg, start=s113.CUT, end=END),
        "full": a75.run(maps, bars, funding, cfg, start=start, end=END),
    }
    screens = []
    for btc_min in (.02, .03, .05):
        for sol_min in (0, .05, .10, .15):
            for breadth_min in (3, 4, 5):
                for multiplier in (0, .25, .5, .75):
                    changed = filtered(maps, bars, btc_min, sol_min, breadth_min, multiplier)
                    early = a75.run(changed, bars, funding, cfg, start=start, end=s113.CUT)
                    screens.append({"btc_168h_min_pct": btc_min*100, "sol_168h_min_pct": sol_min*100,
                                    "positive_breadth_min": breadth_min, "short_multiplier": multiplier,
                                    "early": compact(early)})
    eligible = [x for x in screens if x["early"]["end_usd"] >= 90 and x["early"]["close_mark_mdd_pct"] >= -57]
    # Freeze candidates using training data only. Preserve different breadth and
    # sizing families rather than selecting repeatedly on the holdout.
    ranked = sorted(eligible, key=lambda x: (x["early"]["end_usd"], x["early"]["close_mark_mdd_pct"]), reverse=True)
    finalists, families = [], set()
    for row in ranked:
        family = (row["positive_breadth_min"], row["short_multiplier"])
        if family in families:
            continue
        families.add(family); finalists.append(row)
        if len(finalists) >= 12:
            break
    for row in finalists:
        changed = filtered(maps, bars, row["btc_168h_min_pct"]/100, row["sol_168h_min_pct"]/100,
                           row["positive_breadth_min"], row["short_multiplier"])
        row["holdout_5y"] = compact(a75.run(changed, bars, funding, cfg, start=s113.CUT, end=END))
        row["full_extension"] = compact(a75.run(changed, bars, funding, cfg, start=start, end=END))
        row["holdout_5y_double_cost"] = compact(a75.run(changed, bars, funding, cfg, start=s113.CUT, end=END, stress=True))
        row["full_double_cost"] = compact(a75.run(changed, bars, funding, cfg, start=start, end=END, stress=True))
        row["pass_strict"] = (row["holdout_5y"]["return_pct"] >= baseline["five"]["return_pct"]
                              and row["full_extension"]["return_pct"] > baseline["full"]["return_pct"]
                              and row["full_extension"]["close_mark_mdd_pct"] > baseline["full"]["close_mark_mdd_pct"]
                              and row["holdout_5y_double_cost"]["return_pct"] >= 1_000_000)
        row["pass_candidate"] = (row["holdout_5y"]["return_pct"] >= baseline["five"]["return_pct"]*.95
                                 and row["full_extension"]["return_pct"] > baseline["full"]["return_pct"]*1.25
                                 and row["full_extension"]["close_mark_mdd_pct"] >= -55
                                 and row["holdout_5y_double_cost"]["return_pct"] >= 1_000_000)
    result = {"id":"A-STAGE115-SOL-SHORT-REFINEMENT","generated_at":datetime.now(timezone.utc).isoformat(),
              "research_only":True,"live_changes":False,"screens":len(screens),"eligible":len(eligible),
              "baseline":{k:compact(v) for k,v in baseline.items()},"finalists":finalists,
              "limitations":["All gate inputs use completed 168h returns at the execution boundary.",
                              "The short early extension selects candidates; the later five years are evaluated once per frozen family.",
                              "Underlying A trees are not an untouched holdout."]}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"screens":len(screens),"eligible":len(eligible),"strict":sum(x["pass_strict"] for x in finalists),
                      "candidate":sum(x["pass_candidate"] for x in finalists),"finalists":finalists},ensure_ascii=False))


if __name__ == "__main__":
    main()

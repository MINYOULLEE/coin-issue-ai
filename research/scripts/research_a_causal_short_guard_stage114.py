"""Train causal A short guards on the backward extension, freeze, then test 5y.

Research only. No live state, standards, credentials, or orders are touched.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone

import evaluate_ab_7y as ab
import research_a_drawdown_guard_stage75 as a75
import research_ab_reinforcement_stage113 as s113
import validate_a_exposure_scale_stage68 as a68

OUT = ab.OUT / "A_STAGE114_CAUSAL_SHORT_GUARD.json"
H = ab.H
END = int(datetime(2026, 8, 30, tzinfo=timezone.utc).timestamp() * 1000)


def compact(x):
    return {k: v for k, v in x.items() if k not in ("stop_events", "ledger")}


def guarded(source, bars, scope, lookback, threshold, multiplier):
    result = copy.deepcopy(source)
    targets = a68.SYMBOLS if scope == "all" else ["SOL"]
    for symbol in targets:
        for stamp, value in list(result[symbol].items()):
            if value >= 0:
                continue
            recent = bars["BTC"].get(stamp-H)
            prior = bars["BTC"].get(stamp-(lookback+1)*H)
            if recent and prior and recent["c"] / prior["c"] - 1 >= threshold:
                result[symbol][stamp] = value * multiplier
    return result


def main():
    maps, bars, funding = s113.a_inputs()
    start = min(set.intersection(*(set(bars[s]) for s in a68.SYMBOLS)))
    cfg = {"id": "guard35_075", "scale": 1.4, "dd_trigger": .35,
           "dd_reduced_scale": .75, "dd_recovery": .175}
    early_base = a75.run(maps, bars, funding, cfg, start=start, end=s113.CUT)
    five_base = a75.run(maps, bars, funding, cfg, start=s113.CUT, end=END)
    full_base = a75.run(maps, bars, funding, cfg, start=start, end=END)
    screens = []
    for scope in ("sol", "all"):
        for lookback in (24, 72, 168):
            for threshold in (.03, .05, .10, .15):
                for multiplier in (0.0, .5):
                    changed = guarded(maps, bars, scope, lookback, threshold, multiplier)
                    early = a75.run(changed, bars, funding, cfg, start=start, end=s113.CUT)
                    screens.append({"scope": scope, "lookback_hours": lookback,
                                    "btc_return_threshold_pct": threshold*100,
                                    "short_multiplier": multiplier, "early": compact(early),
                                    "train_improves_return": early["end_usd"] > early_base["end_usd"],
                                    "train_improves_mdd": early["close_mark_mdd_pct"] > early_base["close_mark_mdd_pct"]})
    trained = [x for x in screens if x["train_improves_return"] and x["train_improves_mdd"]]
    ranked = sorted(trained, key=lambda x: (x["early"]["end_usd"], x["early"]["close_mark_mdd_pct"]), reverse=True)
    # Keep both families represented; a broad all-symbol gate must not crowd the
    # diagnosed SOL-only hypothesis out of chronological holdout validation.
    finalists = []
    for scope in ("sol", "all"):
        finalists.extend([x for x in ranked if x["scope"] == scope][:6])
    for row in finalists:
        changed = guarded(maps, bars, row["scope"], row["lookback_hours"], row["btc_return_threshold_pct"]/100, row["short_multiplier"])
        row["holdout_5y"] = compact(a75.run(changed, bars, funding, cfg, start=s113.CUT, end=END))
        row["full_extension"] = compact(a75.run(changed, bars, funding, cfg, start=start, end=END))
        row["holdout_5y_double_cost"] = compact(a75.run(changed, bars, funding, cfg, start=s113.CUT, end=END, stress=True))
        row["full_double_cost"] = compact(a75.run(changed, bars, funding, cfg, start=start, end=END, stress=True))
        row["pass"] = (row["holdout_5y"]["return_pct"] >= five_base["return_pct"]
                       and row["full_extension"]["return_pct"] >= full_base["return_pct"]
                       and row["holdout_5y_double_cost"]["return_pct"] >= 1_000_000
                       and row["full_extension"]["close_mark_mdd_pct"] > full_base["close_mark_mdd_pct"]
                       and row["full_extension"]["hourly_adverse_bound_mdd_pct"] >= -70)
    output = {"id": "A-STAGE114-CAUSAL-SHORT-GUARD", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "live_changes": False,
              "training_range": [datetime.fromtimestamp(start/1000, timezone.utc).isoformat(), datetime.fromtimestamp(s113.CUT/1000, timezone.utc).isoformat()],
              "holdout_range": [datetime.fromtimestamp(s113.CUT/1000, timezone.utc).isoformat(), datetime.fromtimestamp(END/1000, timezone.utc).isoformat()],
              "baseline": {"early": compact(early_base), "holdout_5y": compact(five_base), "full_extension": compact(full_base)},
              "screens": len(screens), "trained": len(trained), "finalists": finalists,
              "limitations": ["BTC momentum is causal at each A execution boundary.",
                              "Candidate selection uses only the short backward extension; the later five years are fixed holdout for this new guard.",
                              "The underlying A trees were developed previously and are not an untouched holdout." ]}
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"baseline": output["baseline"], "screens": len(screens), "trained": len(trained),
                      "finalists": finalists}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Search for lower drawdown without reducing Stage105 one-minute returns."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import optimize_b_delay_stage101 as s101
import repair_b_7y_stage97 as s97
import validate_b_regime_stage105 as s105


ab = s101.ab
OUT = ab.OUT / "B_STAGE106_LOWER_DRAWDOWN_SEARCH.json"
BASELINE = {
    "five_return": 4_827_595.900968802,
    "seven_return": 11_812_856.599994808,
    "five_mdd": -50.860954241435685,
    "seven_mdd": -62.78565676276365,
}


def compact(result):
    return {key: value for key, value in result.items() if key != "ledger"}


def main():
    series, entries, times, _ = s101.delayed_inputs(1)
    entries, blocked = s105.filter_entries(entries)
    features = {symbol: ab.b91.s90.s86.s58.old.prev.features(list(rows.values()))
                for symbol, rows in series.items()}
    exits = s101.s99.learned_exits(series, entries, features)
    rows = []
    for cap in (3.50, 3.75, 4.00, 4.25):
        for trigger in (.20, .25):
            for cooldown in (120, 168, 216):
                fn = s97.runner(exits, cap, trigger, cooldown)
                seven = fn(series, entries, times, 1.15)
                five = fn(series, entries, times, 1.15, start=s101.START_5Y, end=s101.END)
                item = {"gross_cap": cap, "trigger_pct": trigger*100,
                        "cooldown_hours": cooldown, "seven_year": compact(seven),
                        "five_year": compact(five)}
                item["return_not_lower"] = (seven["return_pct"] >= BASELINE["seven_return"]
                                             and five["return_pct"] >= BASELINE["five_return"])
                item["mdd_better"] = (seven["hourly_mark_mdd_pct"] > BASELINE["seven_mdd"]
                                      and five["hourly_mark_mdd_pct"] > BASELINE["five_mdd"])
                item["pass"] = (item["return_not_lower"] and item["mdd_better"]
                                and seven["hourly_adverse_bound_pct"] >= -70
                                and five["hourly_adverse_bound_pct"] >= -70
                                and not seven["liquidation_proxy_count"]
                                and not five["liquidation_proxy_count"])
                rows.append(item)

    passing = [row for row in rows if row["pass"]]
    # Stress only non-dominated passing candidates.
    for row in passing:
        fn = s97.runner(exits, row["gross_cap"], row["trigger_pct"]/100, row["cooldown_hours"])
        row["double_cost_seven_year"] = compact(fn(series, entries, times, 1.15, cost_mult=2))
        row["double_cost_five_year"] = compact(
            fn(series, entries, times, 1.15, cost_mult=2, start=s101.START_5Y, end=s101.END))
        row["stress_pass"] = all(
            row[key]["hourly_adverse_bound_pct"] >= -70
            and row[key]["liquidation_proxy_count"] == 0
            for key in ("double_cost_seven_year", "double_cost_five_year"))

    result = {
        "id": "B-STAGE106-LOWER-DRAWDOWN-WITHOUT-RETURN-LOSS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False,
        "entry_delay_minutes": 1, "blocked_signals": len(blocked),
        "baseline": BASELINE, "screens": rows, "passing": passing,
        "limitations": [
            "Risk parameters are optimized on observed data and require fixed follow-up validation.",
            "Return-not-lower is enforced on both the five-year and full executable extension paths.",
            "No live state, orders, switches, or adopted standards changed.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    ranked = sorted(rows, key=lambda row: (row["pass"], row["seven_year"]["return_pct"]), reverse=True)
    print(json.dumps({"passing": passing, "top": ranked[:8]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

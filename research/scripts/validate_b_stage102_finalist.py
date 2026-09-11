"""Fixed-candidate delay, cost and three-way validation for Stage101's leader."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import evaluate_ab_7y as ab
import repair_b_7y_stage97 as s97
import optimize_b_delay_stage101 as s101


OUT = ab.OUT / "B_STAGE102_FINALIST_VALIDATION.json"
START_5Y = int(datetime(2021, 8, 28, tzinfo=timezone.utc).timestamp() * 1000)
END = int(datetime(2026, 8, 30, tzinfo=timezone.utc).timestamp() * 1000)
PARAMS = {"gross_cap": 3.75, "trigger": .25, "cooldown_hours": 168}


def compact(result):
    return {key: value for key, value in result.items() if key != "ledger"}


def main():
    scenarios = []
    one_minute_inputs = None
    for delay in (0, 1, 3, 5):
        series, entries, times, exits = s101.delayed_inputs(delay)
        if delay == 1:
            one_minute_inputs = (series, entries, times, exits)
        fn = s97.runner(exits, PARAMS["gross_cap"], PARAMS["trigger"], PARAMS["cooldown_hours"])
        scenarios.append({
            "entry_delay_minutes": delay,
            "seven_year": compact(fn(series, entries, times, 1.15)),
            "five_year": compact(fn(series, entries, times, 1.15, start=START_5Y, end=END)),
            "double_cost_seven_year": compact(fn(series, entries, times, 1.15, cost_mult=2)),
            "double_cost_five_year": compact(fn(series, entries, times, 1.15, cost_mult=2,
                                                   start=START_5Y, end=END)),
        })

    series, entries, times, exits = one_minute_inputs
    fn = s97.runner(exits, PARAMS["gross_cap"], PARAMS["trigger"], PARAMS["cooldown_hours"])
    start, end = min(times), max(times) + s97.HOUR
    span = end - start
    bounds = [start, start + span//3, start + 2*span//3, end]
    segments = []
    for index in range(3):
        segments.append({
            "segment": index + 1,
            "start": datetime.fromtimestamp(bounds[index]/1000, timezone.utc).isoformat(),
            "end": datetime.fromtimestamp(bounds[index+1]/1000, timezone.utc).isoformat(),
            "base": compact(fn(series, entries, times, 1.15, start=bounds[index], end=bounds[index+1])),
            "double_cost": compact(fn(series, entries, times, 1.15, cost_mult=2,
                                        start=bounds[index], end=bounds[index+1])),
        })

    def scenario_pass(row):
        return (row["five_year"]["return_pct"] >= 1_000_000
                and row["seven_year"]["return_pct"] >= 1_000_000
                and all(row[key]["hourly_adverse_bound_pct"] >= -70
                        and row[key]["liquidation_proxy_count"] == 0
                        for key in ("five_year", "seven_year", "double_cost_five_year",
                                    "double_cost_seven_year")))

    result = {
        "id": "B-STAGE102-FIXED-FINALIST-VALIDATION",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False,
        "candidate": {"max_entry_gross_equity_ratio": 3.75,
                      "drawdown_trigger_pct": 25, "new_entry_cooldown_hours": 168},
        "scenarios": scenarios, "three_way_one_minute": segments,
        "passes_by_delay": {str(row["entry_delay_minutes"]): scenario_pass(row) for row in scenarios},
        "three_way_all_profitable": all(x["base"]["end_usd"] > 100 and x["double_cost"]["end_usd"] > 100
                                             for x in segments),
        "three_way_all_adverse_under_70": all(
            x[key]["hourly_adverse_bound_pct"] >= -70
            for x in segments for key in ("base", "double_cost")),
        "limitations": [
            "Candidate was selected on observed history; this is fixed rerun and stability validation, not untouched forward validation.",
            "Minute substitution covers ALGO/ADA windows; other Stage93 families remain hourly.",
            "Binance USD-M is a proxy for BingX execution and does not model order-book depth.",
            "No live state, orders, switches, or adopted standards changed.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

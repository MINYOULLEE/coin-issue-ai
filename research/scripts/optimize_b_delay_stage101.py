"""Search Stage99 risk parameters against a one-minute futures-entry delay."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import evaluate_ab_7y as ab
import repair_b_7y_stage97 as s97
import verify_b_7y_stage99_execution as s99


OUT = ab.OUT / "B_STAGE101_DELAY_ROBUST_SEARCH.json"
START_5Y = int(datetime(2021, 8, 28, tzinfo=timezone.utc).timestamp() * 1000)
END = int(datetime(2026, 8, 30, tzinfo=timezone.utc).timestamp() * 1000)


def compact(result):
    return {key: value for key, value in result.items() if key != "ledger"}


def delayed_inputs(delay=1):
    series, _, times, _, ops, entries, _, ada_ops = ab.build_b_inputs()
    candidates = ops["ALGO"] + ada_ops
    windows, unavailable = {}, set()
    for op in candidates:
        key, rows, _ = s99.fetch(op)
        if rows is None:
            unavailable.add(key)
        else:
            windows[key] = rows
    candidates = [op for op in candidates if (op["symbol"], op["entry_ts"]) not in unavailable]
    entries = {stamp: [x for x in rows if (x["symbol"], x["entry_ts"]) not in unavailable]
               for stamp, rows in entries.items()}
    trial = {symbol: dict(rows) for symbol, rows in series.items()}
    for op in candidates:
        minute = windows[(op["symbol"], op["entry_ts"])]
        for hour in range(op["entry_ts"], op["exit_bar"] + s99.HOUR, s99.HOUR):
            bar = s99.aggregate(minute, hour, delay if hour == op["entry_ts"] else 0)
            bar.update({key: value for key, value in trial[op["symbol"]][hour].items() if key not in bar})
            trial[op["symbol"]][hour] = bar
    features = {symbol: ab.b91.s90.s86.s58.old.prev.features(list(rows.values())) for symbol, rows in trial.items()}
    return trial, entries, times, s99.learned_exits(trial, entries, features)


def main():
    series, entries, times, exits = delayed_inputs(1)
    rows = []
    for cap in (3.25, 3.50, 3.75, 4.00):
        for trigger in (.25, .30):
            for cooldown in (168, 240, 336):
                fn = s97.runner(exits, cap, trigger, cooldown)
                seven = fn(series, entries, times, 1.15)
                row = {"gross_cap": cap, "trigger_pct": trigger*100,
                       "cooldown_hours": cooldown, "seven_year": compact(seven)}
                if seven["return_pct"] >= 900_000 and seven["hourly_adverse_bound_pct"] >= -70:
                    five = fn(series, entries, times, 1.15, start=START_5Y, end=END)
                    row["five_year"] = compact(five)
                    if five["return_pct"] >= 1_000_000 and seven["return_pct"] >= 1_000_000:
                        row["double_cost_seven_year"] = compact(fn(series, entries, times, 1.15, cost_mult=2))
                        row["double_cost_five_year"] = compact(
                            fn(series, entries, times, 1.15, cost_mult=2, start=START_5Y, end=END))
                stress7 = row.get("double_cost_seven_year")
                stress5 = row.get("double_cost_five_year")
                row["pass"] = bool(
                    row.get("five_year") and stress7 and stress5
                    and seven["hourly_adverse_bound_pct"] >= -70
                    and row["five_year"]["hourly_adverse_bound_pct"] >= -70
                    and stress7["hourly_adverse_bound_pct"] >= -70
                    and stress5["hourly_adverse_bound_pct"] >= -70
                    and not seven["liquidation_proxy_count"]
                    and not row["five_year"]["liquidation_proxy_count"]
                    and not stress7["liquidation_proxy_count"]
                    and not stress5["liquidation_proxy_count"])
                rows.append(row)
    result = {
        "id": "B-STAGE101-ONE-MINUTE-DELAY-ROBUST-SEARCH",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False,
        "entry_delay_minutes": 1, "screens": rows,
        "passing": [row for row in rows if row["pass"]],
        "limitations": [
            "Parameters are searched on observed history; follow-up three-minute and split validation is required.",
            "Minute substitution covers ALGO/ADA windows; other families remain hourly.",
            "No live state, orders, switches, or adopted standards changed.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    top = sorted(rows, key=lambda row: row["seven_year"]["return_pct"], reverse=True)[:8]
    print(json.dumps({"passing": result["passing"], "top": top}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Five-year companion replay for the Stage99 execution scenarios."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import evaluate_ab_7y as ab
import repair_b_7y_stage97 as s97
import verify_b_7y_stage99_execution as s99


OUT = ab.OUT / "B_STAGE100_FIVE_SEVEN_YEAR_COMPARISON.json"
START_5Y = int(datetime(2021, 8, 28, tzinfo=timezone.utc).timestamp() * 1000)
END = int(datetime(2026, 8, 30, tzinfo=timezone.utc).timestamp() * 1000)


def compact(result):
    return {key: value for key, value in result.items() if key != "ledger"}


def main():
    series, _, times, _, ops, entries, _, ada_ops = ab.build_b_inputs()
    candidates = ops["ALGO"] + ada_ops
    unavailable = []
    windows = {}
    for op in candidates:
        key, rows, _ = s99.fetch(op)
        if rows is None:
            unavailable.append(key)
        else:
            windows[key] = rows
    unavailable = set(unavailable)
    candidates = [op for op in candidates if (op["symbol"], op["entry_ts"]) not in unavailable]
    entries = {stamp: [x for x in rows if (x["symbol"], x["entry_ts"]) not in unavailable]
               for stamp, rows in entries.items()}

    scenarios = []
    for delay in (0, 1, 3, 5):
        trial = {symbol: dict(rows) for symbol, rows in series.items()}
        for op in candidates:
            minute = windows[(op["symbol"], op["entry_ts"])]
            for hour in range(op["entry_ts"], op["exit_bar"] + s99.HOUR, s99.HOUR):
                bar = s99.aggregate(minute, hour, delay if hour == op["entry_ts"] else 0)
                bar.update({key: value for key, value in trial[op["symbol"]][hour].items() if key not in bar})
                trial[op["symbol"]][hour] = bar
        features = {symbol: ab.b91.s90.s86.s58.old.prev.features(list(rows.values())) for symbol, rows in trial.items()}
        exits = s99.learned_exits(trial, entries, features)
        fn = s97.runner(exits, 3.5)
        base = fn(trial, entries, times, 1.15, start=START_5Y, end=END)
        stress = fn(trial, entries, times, 1.15, cost_mult=2, start=START_5Y, end=END)
        scenarios.append({"entry_delay_minutes": delay, "base": compact(base), "double_cost": compact(stress)})

    seven = json.loads((ab.OUT / "B_STAGE99_EXECUTION_VALIDATION.json").read_text(encoding="utf-8"))
    result = {
        "id": "B-STAGE100-FIVE-SEVEN-YEAR-COMPARISON",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False,
        "candidate": seven["candidate"],
        "five_year_range": [datetime.fromtimestamp(START_5Y/1000, timezone.utc).isoformat(),
                             datetime.fromtimestamp(END/1000, timezone.utc).isoformat()],
        "five_year_scenarios": scenarios,
        "seven_year_effective_range": ["2021-05-11T01:00:00+00:00", "2026-08-30T00:00:00+00:00"],
        "seven_year_scenarios": seven["scenarios"],
        "limitations": seven["limitations"] + [
            "The exact B core starts in 2021-05, so the nominal seven-year request has only about 5.3 years of executable Stage93 history.",
            "No live state, orders, switches, or adopted standards changed.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

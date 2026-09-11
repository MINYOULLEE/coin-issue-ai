"""Fixed validation of the Stage104 BTC 24h crash gate finalist."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import optimize_b_delay_stage101 as s101
import repair_b_7y_stage97 as s97


ab = s101.ab
OUT = ab.OUT / "B_STAGE105_REGIME_FINALIST_VALIDATION.json"
START_5Y, END = s101.START_5Y, s101.END
BLOCKED_SYMBOLS = {"BCH", "LINK", "UNI"}


def compact(result):
    return {key: value for key, value in result.items() if key != "ledger"}


def filter_entries(entries):
    btc = {row["t"]: row for row in ab.core.read_candles(ab.SPOT / "BTCUSDT_1h.csv")}
    filtered, blocked = {}, []
    for stamp, rows in entries.items():
        recent, prior = btc.get(stamp-s97.HOUR), btc.get(stamp-25*s97.HOUR)
        btc_return = recent["c"]/prior["c"]-1 if recent and prior else None
        kept = []
        for row in rows:
            if row["symbol"] in BLOCKED_SYMBOLS and btc_return is not None and btc_return <= -.05:
                blocked.append({"symbol": row["symbol"], "entry_ts": row["entry_ts"],
                                "btc_24h_return": btc_return})
            else:
                kept.append(dict(row))
        filtered[stamp] = kept
    return filtered, blocked


def inputs(delay):
    series, entries, times, _ = s101.delayed_inputs(delay)
    filtered, blocked = filter_entries(entries)
    features = {symbol: ab.b91.s90.s86.s58.old.prev.features(list(rows.values()))
                for symbol, rows in series.items()}
    exits = s101.s99.learned_exits(series, filtered, features)
    return series, filtered, times, exits, blocked


def main():
    scenarios, one = [], None
    for delay in (0, 1, 3, 5):
        series, entries, times, exits, blocked = inputs(delay)
        if delay == 1:
            one = series, entries, times, exits
        fn = s97.runner(exits, 3.75, .25, 168)
        scenarios.append({
            "entry_delay_minutes": delay, "blocked_signals": len(blocked),
            "seven_year": compact(fn(series, entries, times, 1.15)),
            "five_year": compact(fn(series, entries, times, 1.15, start=START_5Y, end=END)),
            "double_cost_seven_year": compact(fn(series, entries, times, 1.15, cost_mult=2)),
            "double_cost_five_year": compact(fn(series, entries, times, 1.15, cost_mult=2,
                                                   start=START_5Y, end=END)),
        })

    series, entries, times, exits = one
    fn = s97.runner(exits, 3.75, .25, 168)
    start, end = min(times), max(times)+s97.HOUR
    span = end-start
    bounds = [start, start+span//3, start+2*span//3, end]
    segments = []
    for index in range(3):
        segments.append({
            "segment": index+1,
            "start": datetime.fromtimestamp(bounds[index]/1000, timezone.utc).isoformat(),
            "end": datetime.fromtimestamp(bounds[index+1]/1000, timezone.utc).isoformat(),
            "base": compact(fn(series, entries, times, 1.15, start=bounds[index], end=bounds[index+1])),
            "double_cost": compact(fn(series, entries, times, 1.15, cost_mult=2,
                                        start=bounds[index], end=bounds[index+1])),
        })

    def passes(row):
        return (row["five_year"]["return_pct"] >= 1_000_000
                and row["seven_year"]["return_pct"] >= 1_000_000
                and all(row[key]["hourly_adverse_bound_pct"] >= -70
                        and row[key]["liquidation_proxy_count"] == 0
                        for key in ("five_year", "seven_year", "double_cost_five_year",
                                    "double_cost_seven_year")))
    result = {
        "id": "B-STAGE105-FIXED-BTC-REGIME-FINALIST",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False,
        "candidate": {
            "base": {"max_entry_gross_equity_ratio": 3.75, "drawdown_trigger_pct": 25,
                     "new_entry_cooldown_hours": 168},
            "regime_gate": {"btc_completed_24h_return_lte_pct": -5,
                            "block_new_entries_only": ["BCH", "LINK", "UNI"]},
        },
        "scenarios": scenarios,
        "passes_by_delay": {str(row["entry_delay_minutes"]): passes(row) for row in scenarios},
        "three_way_one_minute": segments,
        "three_way_all_profitable": all(
            row[key]["end_usd"] > 100 for row in segments for key in ("base", "double_cost")),
        "three_way_all_adverse_under_70": all(
            row[key]["hourly_adverse_bound_pct"] >= -70
            for row in segments for key in ("base", "double_cost")),
        "limitations": [
            "The gate was discovered on the early extension and selected after viewing later-history results; no untouched forward data remains.",
            "Minute substitution covers ALGO/ADA windows; other families remain hourly.",
            "No live state, orders, switches, or adopted standards changed.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

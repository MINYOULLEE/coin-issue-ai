"""Fixed validation for the two Stage107 ICP selective-gate finalists."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import optimize_b_delay_stage101 as s101
import repair_b_7y_stage97 as s97

ab = s101.ab
OUT = ab.OUT / "B_STAGE108_SELECTIVE_GATE_VALIDATION.json"
SCOPE = {"BCH", "ICP", "LINK", "UNI"}


def compact(x): return {k: v for k, v in x.items() if k != "ledger"}


def filter_entries(entries, threshold):
    btc = {r["t"]: r for r in ab.core.read_candles(ab.SPOT / "BTCUSDT_1h.csv")}
    out, blocked = {}, 0
    for stamp, rows in entries.items():
        recent, prior = btc.get(stamp-s97.HOUR), btc.get(stamp-73*s97.HOUR)
        ret = recent["c"]/prior["c"]-1 if recent and prior else None
        out[stamp] = []
        for row in rows:
            if row["symbol"] in SCOPE and ret is not None and ret <= threshold: blocked += 1
            else: out[stamp].append(dict(row))
    return out, blocked


def main():
    candidates = []
    for threshold in (-.04, -.06):
        scenarios, one = [], None
        for delay in (0, 1, 3, 5):
            series, entries, times, _ = s101.delayed_inputs(delay)
            entries, blocked = filter_entries(entries, threshold)
            features = {s: ab.b91.s90.s86.s58.old.prev.features(list(rows.values())) for s, rows in series.items()}
            exits = s101.s99.learned_exits(series, entries, features)
            fn = s97.runner(exits, 3.75, .25, 168)
            row = {"delay_minutes": delay, "blocked": blocked,
                   "seven": compact(fn(series, entries, times, 1.15)),
                   "five": compact(fn(series, entries, times, 1.15, start=s101.START_5Y, end=s101.END)),
                   "seven_double_cost": compact(fn(series, entries, times, 1.15, cost_mult=2)),
                   "five_double_cost": compact(fn(series, entries, times, 1.15, cost_mult=2, start=s101.START_5Y, end=s101.END))}
            scenarios.append(row)
            if delay == 1: one = series, entries, times, fn
        series, entries, times, fn = one
        start, end = min(times), max(times)+s97.HOUR
        span = end-start; bounds = [start, start+span//3, start+2*span//3, end]
        thirds = []
        for i in range(3):
            thirds.append({"segment": i+1,
                "base": compact(fn(series, entries, times, 1.15, start=bounds[i], end=bounds[i+1])),
                "double_cost": compact(fn(series, entries, times, 1.15, cost_mult=2, start=bounds[i], end=bounds[i+1]))})
        passes = all(r["five"]["return_pct"] >= 1_000_000 and r["seven"]["return_pct"] >= 1_000_000
                     and all(r[k]["hourly_adverse_bound_pct"] >= -70 and r[k]["liquidation_proxy_count"] == 0
                             for k in ("five", "seven", "five_double_cost", "seven_double_cost")) for r in scenarios)
        candidates.append({"btc_72h_threshold_pct": threshold*100, "scenarios": scenarios, "thirds": thirds,
                           "passes_delays_and_stress": passes,
                           "thirds_profitable": all(x[k]["end_usd"] > 100 for x in thirds for k in ("base", "double_cost"))})
    result = {"id": "B-STAGE108-FIXED-SELECTIVE-GATE", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "live_changes": False,
              "fixed_base": {"gross_cap": 3.75, "drawdown_trigger_pct": 25, "cooldown_hours": 168,
                             "blocked_symbols": sorted(SCOPE), "lookback_hours": 72},
              "candidates": candidates,
              "limitations": ["Candidates were selected on observed history and are not independent forward validation.", "No live state changed."]}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False), flush=True)


if __name__ == "__main__": main()

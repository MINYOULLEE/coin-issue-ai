"""Robustness validation around Stage108 without changing the fixed live strategy."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import optimize_b_delay_stage101 as s101
import repair_b_7y_stage97 as s97

ab = s101.ab
OUT = ab.OUT / "B_STAGE109_NEIGHBORHOOD_AND_CALENDAR_VALIDATION.json"
SCOPE = {"BCH", "ICP", "LINK", "UNI"}


def compact(x): return {k: v for k, v in x.items() if k != "ledger"}


def filtered_entries(entries, btc, hours, threshold):
    out, blocked = {}, 0
    for stamp, rows in entries.items():
        a, b = btc.get(stamp-s97.HOUR), btc.get(stamp-(hours+1)*s97.HOUR)
        ret = a["c"]/b["c"]-1 if a and b else None
        out[stamp] = []
        for row in rows:
            if row["symbol"] in SCOPE and ret is not None and ret <= threshold: blocked += 1
            else: out[stamp].append(dict(row))
    return out, blocked


def main():
    series, raw, times, _ = s101.delayed_inputs(1)
    btc = {r["t"]: r for r in ab.core.read_candles(ab.SPOT / "BTCUSDT_1h.csv")}
    features = {s: ab.b91.s90.s86.s58.old.prev.features(list(rows.values())) for s, rows in series.items()}
    grid = []
    fixed = None
    for hours in (60, 72, 84):
        for threshold in (-.055, -.06, -.065):
            entries, blocked = filtered_entries(raw, btc, hours, threshold)
            exits = s101.s99.learned_exits(series, entries, features)
            fn = s97.runner(exits, 3.75, .25, 168)
            five = fn(series, entries, times, 1.15, start=s101.START_5Y, end=s101.END)
            seven = fn(series, entries, times, 1.15)
            row = {"lookback_hours": hours, "threshold_pct": threshold*100, "blocked": blocked,
                   "five": compact(five), "seven": compact(seven),
                   "pass": five["return_pct"] >= 1_000_000 and seven["return_pct"] >= 1_000_000
                           and five["hourly_adverse_bound_pct"] >= -70 and seven["hourly_adverse_bound_pct"] >= -70
                           and not five["liquidation_proxy_count"] and not seven["liquidation_proxy_count"]}
            grid.append(row)
            if hours == 72 and threshold == -.06: fixed = entries, fn
    entries, fn = fixed
    # UTC calendar years are evaluated independently from $100 to reveal regime dependence.
    first_year = datetime.fromtimestamp(min(times)/1000, timezone.utc).year
    last_year = datetime.fromtimestamp(max(times)/1000, timezone.utc).year
    yearly = []
    for year in range(first_year, last_year+1):
        start = int(datetime(year, 1, 1, tzinfo=timezone.utc).timestamp()*1000)
        end = int(datetime(year+1, 1, 1, tzinfo=timezone.utc).timestamp()*1000)
        if end <= min(times) or start > max(times): continue
        base = fn(series, entries, times, 1.15, start=max(start, min(times)), end=min(end, max(times)+s97.HOUR))
        stress = fn(series, entries, times, 1.15, cost_mult=2, start=max(start, min(times)), end=min(end, max(times)+s97.HOUR))
        yearly.append({"year": year, "base": compact(base), "double_cost": compact(stress)})
    result = {"id": "B-STAGE109-ROBUSTNESS", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "live_changes": False,
              "fixed_candidate": {"lookback_hours": 72, "threshold_pct": -6, "symbols": sorted(SCOPE)},
              "neighborhood": grid, "neighborhood_pass_count": sum(x["pass"] for x in grid),
              "calendar_years": yearly,
              "all_years_profitable": all(x[k]["end_usd"] > 100 for x in yearly for k in ("base", "double_cost")),
              "limitations": ["Historical neighborhood and calendar tests are not future/live validation.", "Partial first and last calendar years are included.", "No live state changed."]}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"neighborhood_pass_count": result["neighborhood_pass_count"], "grid": grid,
                      "years": yearly, "all_years_profitable": result["all_years_profitable"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__": main()

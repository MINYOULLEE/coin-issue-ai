"""Causal volatility overlay search on split extended-synthetic paths."""
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

import replay_mdd30 as a
import research_a_stage78_two_tier_guard as s78
import validate_a_exposure_scale_stage68 as s68
import validate_a_stage80_extended_synthetic as s80

OUT = Path(__file__).resolve().parents[1] / "results" / "a_stage81_volatility_overlay"
BASE = dict(scale=1.45, stop_pct=.15, t1=.275, t2=.375, f1=.85, f2=.50, recovery=.20)
COSTS = {"base": (.0004, .001), "double": (.0008, .003), "severe": (.0015, .01)}


def percentile(xs, q):
    ys = sorted(xs)
    return ys[min(len(ys) - 1, max(0, int(q * (len(ys) - 1))))]


def overlay(bars, maps, window, quantile, factor):
    common = sorted(set.intersection(*[set(bars[s]) for s in s68.SYMBOLS]))
    daily_times = set().union(*[set(maps[s]) for s in s68.SYMBOLS])
    hourly = []
    daily_vols = []
    result = {}
    for i, t in enumerate(common):
        values = []
        if i:
            prev = common[i - 1]
            for symbol in s68.SYMBOLS:
                values.append(abs(math.log(max(bars[symbol][t]["o"] / bars[symbol][prev]["c"], 1e-12))))
                values.append(abs(math.log(max(bars[symbol][prev]["c"] / bars[symbol][prev]["o"], 1e-12))))
        hourly.append(statistics.mean(values) if values else 0.0)
        if t not in daily_times or i < window:
            continue
        recent = statistics.mean(hourly[i - window:i])
        # Compare only with daily observations already known at this boundary.
        threshold = percentile(daily_vols[-30:], quantile) if len(daily_vols) >= 10 else float("inf")
        result[t] = factor if recent > threshold else 1.0
        daily_vols.append(recent)
    return result


def prepare_paths():
    raw, common = s80.s74.load_source()
    trees = a.load_trees()
    paths = []
    number = 0
    for source_window in range(4):
        source = common[source_window * s80.s74.YEAR:source_window * s80.s74.YEAR + s80.s74.WARMUP + s80.s74.YEAR]
        for regime_index, regime in enumerate(s80.REGIMES):
            for replicate in range(4):
                number += 1
                seed = 80000 + source_window * 1000 + regime_index * 100 + replicate
                rows = s80.build(raw, source, seed, regime)
                maps = {s: a.targets(s, rows[s], trees[s], 0) for s in s68.SYMBOLS}
                bars = {s: {x["t"]: x for x in rows[s]} for s in s68.SYMBOLS}
                funding = {s: {} for s in s68.SYMBOLS}
                start = rows[s68.SYMBOLS[0]][0]["t"] + s80.s74.WARMUP * s80.s74.H
                end = start + s80.s74.YEAR * s80.s74.H
                split = "discovery" if source_window < 2 else ("validation" if source_window == 2 else "final")
                paths.append({"window": source_window + 1, "regime": regime, "seed": seed,
                              "split": split, "maps": maps, "bars": bars, "funding": funding,
                              "start": start, "end": end})
                print("prepared", number, "/80", flush=True)
    return paths


def run(path, cfg, cost="base"):
    fee, slip = COSTS[cost]
    ov = overlay(path["bars"], path["maps"], cfg["window"], cfg["quantile"], cfg["factor"])
    return s78.replay(path["maps"], path["bars"], path["funding"], **BASE,
                      fee=fee, stop_slippage=slip, start=path["start"], end=path["end"], scale_overlay=ov)


def score(results):
    profitable = sum(x["end_usd"] > 100 for x in results)
    over70 = sum(x["hourly_adverse_bound_mdd_pct"] < -70 for x in results)
    return profitable * 1000 - over70 * 500 + statistics.median(x["return_pct"] for x in results)


def summarize(results):
    return {"paths": len(results), "profitable": sum(x["end_usd"] > 100 for x in results),
            "mdd_over_70": sum(x["close_mark_mdd_pct"] < -70 for x in results),
            "adverse_over_70": sum(x["hourly_adverse_bound_mdd_pct"] < -70 for x in results),
            "min_return_pct": min(x["return_pct"] for x in results),
            "median_return_pct": statistics.median(x["return_pct"] for x in results),
            "worst_mdd_pct": min(x["close_mark_mdd_pct"] for x in results),
            "worst_adverse_mdd_pct": min(x["hourly_adverse_bound_mdd_pct"] for x in results)}


def main():
    paths = prepare_paths()
    discovery = [p for p in paths if p["split"] == "discovery"]
    grid = []
    for window in (12, 24, 48):
        for quantile in (.75, .85):
            for factor in (.40, .55, .70):
                cfg = {"window": window, "quantile": quantile, "factor": factor}
                values = [run(p, cfg) for p in discovery]
                grid.append({"config": cfg, "score": score(values), "discovery": summarize(values)})
                print("grid", cfg, grid[-1]["score"], flush=True)
    grid.sort(key=lambda x: x["score"], reverse=True)
    finalists = []
    for candidate in grid[:3]:
        cfg = candidate["config"]
        splits = {}
        for split in ("discovery", "validation", "final"):
            ps = [p for p in paths if p["split"] == split]
            splits[split] = {cost: summarize([run(p, cfg, cost) for p in ps]) for cost in COSTS}
        finalists.append({"config": cfg, "selection_score": candidate["score"], "splits": splits})
    result = {"id": "A-STAGE81-VOLATILITY-OVERLAY", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "grid": grid, "finalists": finalists,
              "split_policy": "windows1-2 discovery; window3 validation; window4 final",
              "limitations": ["Transformed history, not future data", "Funding omitted", "Not BingX fills"]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"top": finalists}, ensure_ascii=False))


if __name__ == "__main__":
    main()

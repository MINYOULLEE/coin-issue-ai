"""Search causal drawdown guards for the A 1.4x/3x/15% candidate."""
from __future__ import annotations

import json
import math
import statistics
from datetime import datetime, timezone

import replay_mdd30 as a
import validate_a_exposure_scale_stage68 as s68
import validate_a_scale_stop_stage70 as s70
import ordered_noise_a_candidate_stage74 as s74


CONFIGS = [
    {"id": "fixed_1_35", "scale": 1.35},
    {"id": "guard25_075", "scale": 1.4, "dd_trigger": .25, "dd_reduced_scale": .75, "dd_recovery": .125},
    {"id": "guard30_075", "scale": 1.4, "dd_trigger": .30, "dd_reduced_scale": .75, "dd_recovery": .15},
    {"id": "guard35_075", "scale": 1.4, "dd_trigger": .35, "dd_reduced_scale": .75, "dd_recovery": .175},
    {"id": "guard25_050", "scale": 1.4, "dd_trigger": .25, "dd_reduced_scale": .50, "dd_recovery": .125},
    {"id": "guard30_050", "scale": 1.4, "dd_trigger": .30, "dd_reduced_scale": .50, "dd_recovery": .15},
    {"id": "guard35_050", "scale": 1.4, "dd_trigger": .35, "dd_reduced_scale": .50, "dd_recovery": .175},
]


def kwargs(config):
    return {k: v for k, v in config.items() if k not in ("id", "scale")}


def run(maps, bars, funding, config, start=None, end=None, stress=False):
    extra = {"fee": .0008, "stop_slippage": .003} if stress else {}
    return s70.replay(maps, bars, funding, config["scale"], .15, start=start, end=end,
                      **kwargs(config), **extra)


def synthetic_markets():
    raw, common = s74.load_source()
    trees = a.load_trees()
    result = []
    for window_index in range(4):
        source = common[window_index * s74.YEAR:window_index * s74.YEAR + s74.WARMUP + s74.YEAR]
        for replicate in range(s74.REPLICATES):
            seed = 74000 + window_index * 100 + replicate
            rows = s74.build_variant(raw, source, seed)
            maps = {s: a.targets(s, rows[s], trees[s], 0) for s in s68.SYMBOLS}
            bars = {s: {x["t"]: x for x in rows[s]} for s in s68.SYMBOLS}
            first = rows[s68.SYMBOLS[0]][0]["t"] + s74.WARMUP * s74.H
            result.append({"window": window_index + 1, "replicate": replicate + 1, "seed": seed,
                           "maps": maps, "bars": bars, "funding": {s: {} for s in s68.SYMBOLS},
                           "start": first, "end": first + s74.YEAR * s74.H})
            print("prepared", len(result), flush=True)
    return result


def dist(values):
    xs = sorted(values)
    return {"min": xs[0], "median": statistics.median(xs), "mean": statistics.mean(xs), "max": xs[-1]}


def main():
    actual_maps, actual_bars, actual_funding = s68.load()
    markets = synthetic_markets()
    rows = []
    for config in CONFIGS:
        full = run(actual_maps, actual_bars, actual_funding, config)
        full_stress = run(actual_maps, actual_bars, actual_funding, config, stress=True)
        paths = []
        for market in markets:
            base = run(market["maps"], market["bars"], market["funding"], config, market["start"], market["end"])
            stress = run(market["maps"], market["bars"], market["funding"], config, market["start"], market["end"], True)
            paths.append({"window": market["window"], "replicate": market["replicate"], "seed": market["seed"],
                          "base": base, "stress": stress})
        row = {"config": config, "historical_5y": full, "historical_5y_stress": full_stress,
               "ordered_synthetic": {
                   "paths": len(paths), "profitable": sum(x["base"]["end_usd"] > 100 for x in paths),
                   "stress_profitable": sum(x["stress"]["end_usd"] > 100 for x in paths),
                   "mdd_over_70": sum(x["base"]["close_mark_mdd_pct"] < -70 for x in paths),
                   "adverse_mdd_over_70": sum(x["base"]["hourly_adverse_bound_mdd_pct"] < -70 for x in paths),
                   "stress_mdd_over_70": sum(x["stress"]["close_mark_mdd_pct"] < -70 for x in paths),
                   "return_pct": dist([x["base"]["return_pct"] for x in paths]),
                   "mdd_pct": dist([x["base"]["close_mark_mdd_pct"] for x in paths]),
                   "adverse_mdd_pct": dist([x["base"]["hourly_adverse_bound_mdd_pct"] for x in paths]),
                   "stress_return_pct": dist([x["stress"]["return_pct"] for x in paths]),
               }, "path_results": paths}
        row["pass"] = (full_stress["return_pct"] >= 1_000_000 and full["close_mark_mdd_pct"] >= -70
                       and row["ordered_synthetic"]["profitable"] == len(paths)
                       and row["ordered_synthetic"]["stress_profitable"] == len(paths)
                       and row["ordered_synthetic"]["mdd_over_70"] == 0
                       and row["ordered_synthetic"]["adverse_mdd_over_70"] == 0
                       and row["ordered_synthetic"]["stress_mdd_over_70"] == 0)
        rows.append(row)
        print(config["id"], row["pass"], flush=True)
    result = {"id": "A-DRAWDOWN-GUARD-STAGE75", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "acceptance": {"historical_stress_return_floor_pct": 1_000_000,
              "mdd_floor_pct": -70, "all_ordered_synthetic_paths_profitable": True}, "rows": rows,
              "limitations": ["All guard thresholds were compared on the same historical and synthetic paths; selection bias remains.",
                              "Guard reacts causally after observed drawdown and changes exposure only at the next A daily boundary.",
                              "Ordered synthetic paths are perturbed history, not independent future markets."]}
    out = s68.DIR.parent / "a_drawdown_guard_stage75"
    out.mkdir(exist_ok=True)
    (out / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps([{"id": x["config"]["id"], "pass": x["pass"],
                       "ret5": x["historical_5y"]["return_pct"], "stress5": x["historical_5y_stress"]["return_pct"],
                       "mdd5": x["historical_5y"]["close_mark_mdd_pct"],
                       "synthetic": x["ordered_synthetic"]} for x in rows], ensure_ascii=False))


if __name__ == "__main__":
    main()

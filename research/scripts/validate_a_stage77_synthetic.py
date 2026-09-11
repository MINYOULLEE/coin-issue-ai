"""Ordered synthetic validation for corrected A Stage77 guard candidates."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

import research_a_drawdown_guard_stage75 as s75
import validate_a_exposure_scale_stage68 as s68
import validate_a_scale_stop_stage70 as s70

OUT = Path(__file__).resolve().parents[1] / "results" / "a_stage77_corrected_guard" / "SYNTHETIC.json"
CANDIDATES = {
    "return": {"scale": 1.45, "stop": .15, "dd_trigger": .35, "dd_reduced_scale": .75, "dd_recovery": .175},
    "balanced": {"scale": 1.45, "stop": .15, "dd_trigger": .35, "dd_reduced_scale": .50, "dd_recovery": .175},
    "early_guard": {"scale": 1.45, "stop": .15, "dd_trigger": .25, "dd_reduced_scale": .75, "dd_recovery": .125},
}
COSTS = {"base": (.0004, .001), "double": (.0008, .003), "severe": (.0015, .01)}


def replay(maps, bars, funding, cfg, start=None, end=None, stress="base"):
    fee, slip = COSTS[stress]
    return s70.replay(
        maps, bars, funding, cfg["scale"], cfg["stop"], fee=fee,
        stop_slippage=slip, start=start, end=end,
        dd_trigger=cfg["dd_trigger"], dd_reduced_scale=cfg["dd_reduced_scale"],
        dd_recovery=cfg["dd_recovery"],
    )


def dist(values):
    values = sorted(values)
    return {"min": values[0], "median": statistics.median(values),
            "mean": statistics.mean(values), "max": values[-1]}


def main():
    maps, bars, funding = s68.load()
    times = sorted(set.intersection(*[set(bars[s]) for s in s68.SYMBOLS]))
    cuts = [times[0] + int((times[-1] - times[0]) * i / 3) for i in range(4)]
    markets = s75.synthetic_markets()
    results = {}
    for name, cfg in CANDIDATES.items():
        historical = {k: replay(maps, bars, funding, cfg, stress=k) for k in COSTS}
        thirds = {k: [replay(maps, bars, funding, cfg, cuts[i], cuts[i + 1], k)
                      for i in range(3)] for k in ("base", "severe")}
        paths = []
        for i, market in enumerate(markets, 1):
            paths.append({k: replay(market["maps"], market["bars"], market["funding"], cfg,
                                    market["start"], market["end"], k) for k in COSTS})
            if i % 8 == 0:
                print(name, "validated", i, "/", len(markets), flush=True)
        synthetic = {"paths": len(paths)}
        for cost in COSTS:
            synthetic[cost] = {
                "profitable": sum(x[cost]["end_usd"] > 100 for x in paths),
                "mdd_over_70": sum(x[cost]["close_mark_mdd_pct"] < -70 for x in paths),
                "adverse_over_70": sum(x[cost]["hourly_adverse_bound_mdd_pct"] < -70 for x in paths),
                "return_pct": dist([x[cost]["return_pct"] for x in paths]),
                "mdd_pct": dist([x[cost]["close_mark_mdd_pct"] for x in paths]),
                "adverse_mdd_pct": dist([x[cost]["hourly_adverse_bound_mdd_pct"] for x in paths]),
            }
        passed = (
            historical["base"]["return_pct"] > 2_143_508.58
            and historical["double"]["return_pct"] > 1_033_997.04
            and historical["severe"]["end_usd"] > 100
            and historical["base"]["max_simultaneous_adverse_margin_equity_ratio_at_3x"] <= .95
            and all(x["end_usd"] > 100 and x["close_mark_mdd_pct"] >= -70 for x in thirds["severe"])
            and all(synthetic[k]["profitable"] == len(paths)
                    and synthetic[k]["mdd_over_70"] == 0
                    and synthetic[k]["adverse_over_70"] == 0 for k in COSTS)
        )
        results[name] = {"config": cfg, "historical": historical, "thirds": thirds,
                         "synthetic": synthetic, "pass": passed}
    output = {
        "id": "A-STAGE77-CORRECTED-GUARD-SYNTHETIC",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "guard_semantics": "effective scale = normal scale * dd_reduced_scale",
        "results": results,
        "limitations": ["Perturbed ordered history is not unseen future data",
                        "Cost stress proxies latency and adverse fills"],
    }
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({name: {"pass": value["pass"],
        "historical_return": value["historical"]["base"]["return_pct"],
        "historical_mdd": value["historical"]["base"]["close_mark_mdd_pct"],
        "margin_peak": value["historical"]["base"]["max_simultaneous_adverse_margin_equity_ratio_at_3x"],
        "synthetic": value["synthetic"]} for name, value in results.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()

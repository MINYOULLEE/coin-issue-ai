"""Synthetic ordered-path validation for top A Stage78 two-tier guards."""
from __future__ import annotations

import json
import statistics
from datetime import datetime, timezone
from pathlib import Path

import research_a_drawdown_guard_stage75 as s75
import research_a_stage78_two_tier_guard as s78
import validate_a_exposure_scale_stage68 as s68

OUT = Path(__file__).resolve().parents[1] / "results" / "a_stage78_two_tier_guard" / "SYNTHETIC.json"
CANDIDATES = {
    "top": dict(scale=1.45, stop_pct=.15, t1=.30, t2=.40, f1=.80, f2=.50, recovery=.175),
    "recovery15": dict(scale=1.45, stop_pct=.15, t1=.30, t2=.40, f1=.80, f2=.50, recovery=.15),
    "cost_focus": dict(scale=1.45, stop_pct=.15, t1=.30, t2=.40, f1=.90, f2=.50, recovery=.15),
}
COSTS = {"base": (.0004, .001), "double": (.0008, .003), "severe": (.0015, .01)}


def run(maps, bars, funding, cfg, cost, start=None, end=None):
    fee, slip = COSTS[cost]
    return s78.replay(maps, bars, funding, **cfg, fee=fee, stop_slippage=slip, start=start, end=end)


def dist(xs):
    xs = sorted(xs)
    return {"min": xs[0], "median": statistics.median(xs), "mean": statistics.mean(xs), "max": xs[-1]}


def main():
    maps, bars, funding = s68.load()
    markets = s75.synthetic_markets()
    results = {}
    for name, cfg in CANDIDATES.items():
        historical = {c: run(maps, bars, funding, cfg, c) for c in COSTS}
        paths = []
        for i, m in enumerate(markets, 1):
            paths.append({c: run(m["maps"], m["bars"], m["funding"], cfg, c, m["start"], m["end"])
                          for c in COSTS})
            if i % 8 == 0:
                print(name, i, "/", len(markets), flush=True)
        synthetic = {"paths": len(paths)}
        for c in COSTS:
            synthetic[c] = {
                "profitable": sum(x[c]["end_usd"] > 100 for x in paths),
                "mdd_over_70": sum(x[c]["close_mark_mdd_pct"] < -70 for x in paths),
                "adverse_over_70": sum(x[c]["hourly_adverse_bound_mdd_pct"] < -70 for x in paths),
                "return_pct": dist([x[c]["return_pct"] for x in paths]),
                "mdd_pct": dist([x[c]["close_mark_mdd_pct"] for x in paths]),
                "adverse_mdd_pct": dist([x[c]["hourly_adverse_bound_mdd_pct"] for x in paths]),
            }
        passed = (historical["base"]["return_pct"] > 2_548_905.03
                  and historical["double"]["return_pct"] > 1_181_201.80
                  and historical["base"]["max_simultaneous_adverse_margin_equity_ratio_at_3x"] <= .95
                  and all(synthetic[c]["profitable"] == 32 and synthetic[c]["mdd_over_70"] == 0
                          and synthetic[c]["adverse_over_70"] == 0 for c in COSTS))
        results[name] = {"config": cfg, "historical": historical, "synthetic": synthetic, "pass": passed}
    output = {"id": "A-STAGE78-TWO-TIER-SYNTHETIC", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "results": results,
              "limitations": ["Perturbed ordered history is not future data", "Costs proxy execution delay"]}
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({n: {"pass": v["pass"], "return": v["historical"]["base"]["return_pct"],
        "mdd": v["historical"]["base"]["close_mark_mdd_pct"], "margin": v["historical"]["base"]["max_simultaneous_adverse_margin_equity_ratio_at_3x"],
        "synthetic": v["synthetic"]} for n, v in results.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()

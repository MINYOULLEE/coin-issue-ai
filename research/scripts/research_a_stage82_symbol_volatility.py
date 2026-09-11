"""Research-only symbol-selective causal volatility overlay for A Stage79."""
from __future__ import annotations
import json
import math
import statistics
from datetime import datetime, timezone
from pathlib import Path

import research_a_stage78_two_tier_guard as s78
import research_a_stage81_volatility_overlay as s81
import validate_a_exposure_scale_stage68 as s68

OUT = Path(__file__).resolve().parents[1] / "results" / "a_stage82_symbol_volatility"


def symbol_overlay(bars, maps, window, quantile, factor):
    common = sorted(set.intersection(*[set(bars[s]) for s in s68.SYMBOLS]))
    index = {t: i for i, t in enumerate(common)}
    returns = {s: [] for s in s68.SYMBOLS}
    for s in s68.SYMBOLS:
        for t in common:
            x = bars[s][t]
            returns[s].append(abs(math.log(max(x["c"] / x["o"], 1e-12))))
    history = {s: [] for s in s68.SYMBOLS}
    result = {}
    decision_times = sorted(set().union(*[set(maps[s]) for s in s68.SYMBOLS]))
    for t in decision_times:
        i = index.get(t)
        if i is None or i < window:
            continue
        item = {}
        for s in s68.SYMBOLS:
            recent = statistics.mean(returns[s][i-window:i])
            threshold = s81.percentile(history[s][-30:], quantile) if len(history[s]) >= 10 else float("inf")
            item[s] = factor if recent > threshold else 1.0
            history[s].append(recent)
        result[t] = item
    return result


def run(path, cfg, cost="base"):
    fee, slip = s81.COSTS[cost]
    ov = symbol_overlay(path["bars"], path["maps"], **cfg)
    return s78.replay(path["maps"], path["bars"], path["funding"], **s81.BASE,
                      fee=fee, stop_slippage=slip, start=path["start"], end=path["end"], scale_overlay=ov)


def main():
    paths = s81.prepare_paths()
    discovery = [p for p in paths if p["split"] == "discovery"]
    grid = []
    for window in (12, 24, 48):
        for quantile in (.75, .85):
            for factor in (.40, .60, .80):
                cfg = {"window": window, "quantile": quantile, "factor": factor}
                values = [run(p, cfg) for p in discovery]
                grid.append({"config": cfg, "score": s81.score(values), "discovery": s81.summarize(values)})
                print("grid", cfg, grid[-1]["score"], flush=True)
    grid.sort(key=lambda x: x["score"], reverse=True)
    finalists = []
    for candidate in grid[:3]:
        cfg = candidate["config"]
        splits = {}
        for split in ("discovery", "validation", "final"):
            ps = [p for p in paths if p["split"] == split]
            splits[split] = {cost: s81.summarize([run(p, cfg, cost) for p in ps]) for cost in s81.COSTS}
        finalists.append({"config": cfg, "selection_score": candidate["score"], "splits": splits})
    result = {"id": "A-STAGE82-SYMBOL-VOLATILITY", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "grid": grid, "finalists": finalists,
              "split_policy": "windows1-2 discovery; window3 validation; window4 final",
              "limitations": ["Transformed history, not future data", "Funding omitted", "Not BingX fills"]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"top": finalists}, ensure_ascii=False))

if __name__ == "__main__": main()

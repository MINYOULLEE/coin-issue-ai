"""Extended transformed-market validation for A Stage79 versus live A Stage75."""
from __future__ import annotations

import json
import math
import random
import statistics
from datetime import datetime, timezone
from pathlib import Path

import ordered_noise_a_candidate_stage74 as s74
import replay_mdd30 as a
import research_a_stage78_two_tier_guard as s78
import validate_a_exposure_scale_stage68 as s68
import validate_a_scale_stop_stage70 as s70

OUT = Path(__file__).resolve().parents[1] / "results" / "a_stage80_extended_synthetic"
REGIMES = {
    "calm": {"weekly": (.50, .85), "common": .00006, "idio": .00005, "flip": .00, "wick": (.70, 1.00)},
    "mixed": {"weekly": (.70, 1.35), "common": .00018, "idio": .00012, "flip": .03, "wick": (.80, 1.30)},
    "volatile": {"weekly": (1.10, 1.75), "common": .00035, "idio": .00025, "flip": .05, "wick": (1.05, 1.65)},
    "whipsaw": {"weekly": (.85, 1.30), "common": .00030, "idio": .00030, "flip": .15, "wick": (1.00, 1.55)},
    "correlation_break": {"weekly": (.65, 1.45), "common": .00003, "idio": .00040, "flip": .08, "wick": (.85, 1.45)},
}
COSTS = {"base": (.0004, .001), "double": (.0008, .003), "severe": (.0015, .01)}
STAGE79 = dict(scale=1.45, stop_pct=.15, t1=.275, t2=.375, f1=.85, f2=.50, recovery=.20)


def build(raw, source, seed, regime):
    cfg = REGIMES[regime]
    rng = random.Random(seed)
    epoch = 1_700_006_400_000
    prices = {s: raw[s][source[0]]["o"] for s in s68.SYMBOLS}
    rows = {s: [] for s in s68.SYMBOLS}
    weekly = 1.0
    symbol_scale = {s: 1.0 for s in s68.SYMBOLS}
    for i, source_t in enumerate(source):
        if i % 168 == 0:
            weekly = rng.uniform(*cfg["weekly"])
            if regime == "correlation_break":
                symbol_scale = {s: rng.uniform(.65, 1.45) for s in s68.SYMBOLS}
        common_noise = rng.gauss(0, cfg["common"])
        t = epoch + i * s74.H
        for symbol in s68.SYMBOLS:
            x = raw[symbol][source_t]
            source_ret = math.log(max(x["c"] / x["o"], 1e-12))
            if rng.random() < cfg["flip"]:
                source_ret *= -1
            log_ret = source_ret * weekly * symbol_scale[symbol]
            log_ret += common_noise + rng.gauss(0, cfg["idio"])
            open_price = prices[symbol]
            close_price = open_price * math.exp(log_ret)
            wick_scale = weekly * rng.uniform(*cfg["wick"])
            upper = math.log(max(x["h"] / max(x["o"], x["c"]), 1.0)) * wick_scale
            lower = math.log(max(min(x["o"], x["c"]) / x["l"], 1.0)) * wick_scale
            high = max(open_price, close_price) * math.exp(upper)
            low = min(open_price, close_price) / math.exp(lower)
            volume = x["v"] * math.exp(rng.gauss(0, .20))
            rows[symbol].append({"t": t, "o": open_price, "h": high, "l": low,
                                 "c": close_price, "v": volume, "q": volume * close_price})
            prices[symbol] = close_price
    return rows


def prepare(rows, trees):
    maps = {s: a.targets(s, rows[s], trees[s], 0) for s in s68.SYMBOLS}
    bars = {s: {x["t"]: x for x in rows[s]} for s in s68.SYMBOLS}
    funding = {s: {} for s in s68.SYMBOLS}
    start = rows[s68.SYMBOLS[0]][0]["t"] + s74.WARMUP * s74.H
    end = start + s74.YEAR * s74.H
    return maps, bars, funding, start, end


def replay(prepared, strategy, cost):
    maps, bars, funding, start, end = prepared
    fee, slip = COSTS[cost]
    if strategy == "stage79":
        return s78.replay(maps, bars, funding, **STAGE79, fee=fee, stop_slippage=slip, start=start, end=end)
    return s70.replay(maps, bars, funding, 1.4, .15, fee=fee, stop_slippage=slip,
                      start=start, end=end, dd_trigger=.35, dd_reduced_scale=.75, dd_recovery=.175)


def dist(xs):
    xs = sorted(xs)
    return {"min": xs[0], "median": statistics.median(xs), "mean": statistics.mean(xs), "max": xs[-1]}


def main():
    raw, common = s74.load_source()
    trees = a.load_trees()
    paths = []
    number = 0
    for window in range(4):
        source = common[window * s74.YEAR:window * s74.YEAR + s74.WARMUP + s74.YEAR]
        for regime_index, regime in enumerate(REGIMES):
            for replicate in range(4):
                number += 1
                seed = 80000 + window * 1000 + regime_index * 100 + replicate
                rows = build(raw, source, seed, regime)
                prepared = prepare(rows, trees)
                item = {"window": window + 1, "regime": regime, "replicate": replicate + 1, "seed": seed}
                for strategy in ("stage75", "stage79"):
                    item[strategy] = {cost: replay(prepared, strategy, cost) for cost in COSTS}
                paths.append(item)
                print("path", number, "/", 80, regime, flush=True)
    summary = {}
    for strategy in ("stage75", "stage79"):
        summary[strategy] = {}
        for cost in COSTS:
            vals = [x[strategy][cost] for x in paths]
            summary[strategy][cost] = {
                "profitable": sum(v["end_usd"] > 100 for v in vals),
                "mdd_over_70": sum(v["close_mark_mdd_pct"] < -70 for v in vals),
                "adverse_over_70": sum(v["hourly_adverse_bound_mdd_pct"] < -70 for v in vals),
                "return_pct": dist([v["return_pct"] for v in vals]),
                "mdd_pct": dist([v["close_mark_mdd_pct"] for v in vals]),
                "adverse_mdd_pct": dist([v["hourly_adverse_bound_mdd_pct"] for v in vals]),
            }
    by_regime = []
    for regime in REGIMES:
        xs = [x for x in paths if x["regime"] == regime]
        by_regime.append({"regime": regime, "paths": len(xs),
            "stage79_profitable_severe": sum(x["stage79"]["severe"]["end_usd"] > 100 for x in xs),
            "stage79_severe_return": dist([x["stage79"]["severe"]["return_pct"] for x in xs]),
            "stage79_severe_adverse_mdd": dist([x["stage79"]["severe"]["hourly_adverse_bound_mdd_pct"] for x in xs]),
            "stage79_beats_stage75_base": sum(x["stage79"]["base"]["end_usd"] > x["stage75"]["base"]["end_usd"] for x in xs)})
    passed = (summary["stage79"]["base"]["profitable"] == 80
              and summary["stage79"]["severe"]["profitable"] == 80
              and summary["stage79"]["severe"]["mdd_over_70"] == 0
              and summary["stage79"]["severe"]["adverse_over_70"] == 0)
    result = {"id": "A-STAGE80-EXTENDED-SYNTHETIC", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "paths": len(paths), "regimes": REGIMES, "pass": passed,
              "summary": summary, "by_regime": by_regime, "path_results": paths,
              "limitations": ["Transformed history is not independent future data", "Funding omitted",
                              "Hourly OHLC cannot resolve cross-symbol intrahour order", "Not BingX fills"]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pass": passed, "summary": summary, "by_regime": by_regime}, ensure_ascii=False))


if __name__ == "__main__":
    main()

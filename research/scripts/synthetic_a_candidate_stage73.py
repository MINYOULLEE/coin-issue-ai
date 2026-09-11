"""Synthetic one-year block-bootstrap validation for the A Stage70 candidate."""
from __future__ import annotations

import json
import math
import random
import statistics
from datetime import datetime, timezone

import replay_mdd30 as a
import validate_a_exposure_scale_stage68 as s68
import validate_a_scale_stop_stage70 as s70


H = 3_600_000
WARMUP = 720
YEAR = 365 * 24
PATHS = 30


def source_rows():
    raw = {}
    for symbol in s68.SYMBOLS:
        rows = json.loads((s68.DIR / "data" / symbol / "hours.json").read_text())
        raw[symbol] = {int(x[0]): {"o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4]),
                                        "v": float(x[5]), "q": float(x[7])} for x in rows}
    common = sorted(set.intersection(*(set(raw[s]) for s in s68.SYMBOLS)))
    return raw, common


def indices(rng, n_source, n_target):
    result = []
    while len(result) < n_target:
        length = rng.choice((24, 48, 72, 120, 168))
        start = rng.randrange(1, n_source - length)
        result.extend(range(start, start + length))
    return result[:n_target]


def make_path(seed, raw, common):
    rng = random.Random(seed)
    picked = indices(rng, len(common), WARMUP + YEAR)
    start_prices = {s: raw[s][common[picked[0]]]["o"] for s in s68.SYMBOLS}
    prices = dict(start_prices)
    rows = {s: [] for s in s68.SYMBOLS}
    funding = {s: {} for s in s68.SYMBOLS}
    trees = a.load_trees()
    epoch = 1_700_000_000_000 // H * H
    block_scale = 1.0
    previous_index = None
    for i, source_index in enumerate(picked):
        if previous_index is None or source_index != previous_index + 1:
            block_scale = rng.uniform(.75, 1.30)
        t = epoch + i * H
        for symbol in s68.SYMBOLS:
            x = raw[symbol][common[source_index]]
            source_open = x["o"]
            log_close = math.log(max(x["c"] / source_open, 1e-12)) * block_scale
            open_price = prices[symbol]
            close_price = open_price * math.exp(log_close)
            upper = math.log(max(x["h"] / max(x["o"], x["c"]), 1.0)) * block_scale
            lower = math.log(max(min(x["o"], x["c"]) / x["l"], 1.0)) * block_scale
            high = max(open_price, close_price) * math.exp(upper)
            low = min(open_price, close_price) / math.exp(lower)
            volume = x["v"] * math.exp(rng.gauss(0, .12))
            rows[symbol].append({"t": t, "o": open_price, "h": high, "l": low, "c": close_price,
                                 "v": volume, "q": volume * close_price})
            prices[symbol] = close_price
        previous_index = source_index
    maps = {s: a.targets(s, rows[s], trees[s], 0) for s in s68.SYMBOLS}
    bars = {s: {x["t"]: x for x in rows[s]} for s in s68.SYMBOLS}
    start = epoch + WARMUP * H
    end = start + YEAR * H
    candidate = s70.replay(maps, bars, funding, 1.4, .15, start=start, end=end)
    stressed = s70.replay(maps, bars, funding, 1.4, .15, fee=.0008, stop_slippage=.003, start=start, end=end)
    baseline = s70.replay(maps, bars, funding, 1.0, .99, start=start, end=end)
    return {"seed": seed, "candidate": candidate, "stressed": stressed, "baseline_no_stop": baseline,
            "candidate_beats_baseline": candidate["end_usd"] > baseline["end_usd"]}


def compact(xs, key1, key2):
    vals = [x[key1][key2] for x in xs]
    ordered = sorted(vals)
    return {"min": min(vals), "p10": ordered[max(0, math.ceil(.10 * len(vals)) - 1)],
            "median": statistics.median(vals), "mean": statistics.mean(vals), "max": max(vals)}


def main():
    raw, common = source_rows()
    paths = []
    for seed in range(73001, 73001 + PATHS):
        paths.append(make_path(seed, raw, common))
        print("path", len(paths), flush=True)
    result = {
        "id": "A-SYNTHETIC-STAGE73", "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "synthetic_years": PATHS, "hours_per_evaluated_year": YEAR,
        "candidate": "A 1.4x notional / 3x isolated / 15% emergency stop",
        "method": "Synchronized 24-168h block bootstrap of five Binance USD-M markets with random 0.75-1.30 volatility scaling; 720h warmup excluded.",
        "summary": {
            "candidate_return_pct": compact(paths, "candidate", "return_pct"),
            "candidate_mdd_pct": compact(paths, "candidate", "close_mark_mdd_pct"),
            "stress_return_pct": compact(paths, "stressed", "return_pct"),
            "baseline_return_pct": compact(paths, "baseline_no_stop", "return_pct"),
            "profitable_candidate_years": sum(x["candidate"]["end_usd"] > 100 for x in paths),
            "profitable_stress_years": sum(x["stressed"]["end_usd"] > 100 for x in paths),
            "candidate_beats_baseline_years": sum(x["candidate_beats_baseline"] for x in paths),
            "candidate_ruin_years": sum(x["candidate"]["end_usd"] <= 0 for x in paths),
            "stress_ruin_years": sum(x["stressed"]["end_usd"] <= 0 for x in paths),
        },
        "paths": paths,
        "limitations": ["Synthetic years are transformations of historical market blocks, not truly unseen future data.",
                        "Funding is set to zero because resampled funding/price time alignment would be artificial; double-cost stress remains.",
                        "Hourly OHLC stop ordering and current BingX quantity grid limitations from Stage70 remain."],
    }
    out = s68.DIR.parent / "a_synthetic_stage73"
    out.mkdir(exist_ok=True)
    (out / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result["summary"], ensure_ascii=False))


if __name__ == "__main__":
    main()

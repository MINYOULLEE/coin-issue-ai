"""Order-preserving synthetic one-year validation for the A Stage70 candidate."""
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
REPLICATES = 8


def load_source():
    raw = {}
    for symbol in s68.SYMBOLS:
        source = json.loads((s68.DIR / "data" / symbol / "hours.json").read_text())
        raw[symbol] = {int(x[0]): {"o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4]),
                                        "v": float(x[5]), "q": float(x[7])} for x in source}
    common = sorted(set.intersection(*(set(raw[s]) for s in s68.SYMBOLS)))
    return raw, common


def build_variant(raw, source_times, seed):
    rng = random.Random(seed)
    epoch = 1_700_006_400_000  # UTC 00:00 boundary
    prices = {s: raw[s][source_times[0]]["o"] for s in s68.SYMBOLS}
    rows = {s: [] for s in s68.SYMBOLS}
    weekly_scale = 1.0
    for i, source_t in enumerate(source_times):
        if i % 168 == 0:
            weekly_scale = rng.uniform(.85, 1.15)
        common_noise = rng.gauss(0, .00012)
        t = epoch + i * H
        for symbol in s68.SYMBOLS:
            x = raw[symbol][source_t]
            # Keep the chronological sign/regime structure; perturb magnitude,
            # small common/idio noise, wicks and volume only.
            log_ret = math.log(max(x["c"] / x["o"], 1e-12)) * weekly_scale
            log_ret += common_noise + rng.gauss(0, .00008)
            open_price = prices[symbol]
            close_price = open_price * math.exp(log_ret)
            wick_scale = weekly_scale * rng.uniform(.92, 1.08)
            upper = math.log(max(x["h"] / max(x["o"], x["c"]), 1.0)) * wick_scale
            lower = math.log(max(min(x["o"], x["c"]) / x["l"], 1.0)) * wick_scale
            high = max(open_price, close_price) * math.exp(upper)
            low = min(open_price, close_price) / math.exp(lower)
            volume = x["v"] * math.exp(rng.gauss(0, .10))
            rows[symbol].append({"t": t, "o": open_price, "h": high, "l": low, "c": close_price,
                                 "v": volume, "q": volume * close_price})
            prices[symbol] = close_price
    return rows


def replay_variant(rows):
    trees = a.load_trees()
    maps = {s: a.targets(s, rows[s], trees[s], 0) for s in s68.SYMBOLS}
    bars = {s: {x["t"]: x for x in rows[s]} for s in s68.SYMBOLS}
    funding = {s: {} for s in s68.SYMBOLS}
    first = rows[s68.SYMBOLS[0]][0]["t"] + WARMUP * H
    end = first + YEAR * H
    return {
        "candidate": s70.replay(maps, bars, funding, 1.4, .15, start=first, end=end),
        "stress": s70.replay(maps, bars, funding, 1.4, .15, fee=.0008, stop_slippage=.003, start=first, end=end),
        "baseline": s70.replay(maps, bars, funding, 1.0, .99, start=first, end=end),
    }


def stats(paths, group, key):
    vals = sorted(x[group][key] for x in paths)
    return {"min": vals[0], "p10": vals[max(0, math.ceil(.1 * len(vals)) - 1)],
            "median": statistics.median(vals), "mean": statistics.mean(vals), "max": vals[-1]}


def main():
    raw, common = load_source()
    # Four non-overlapping consecutive evaluation years, each with its own
    # immediately preceding 720-hour warmup.  Chronological order is untouched.
    windows = []
    for year_index in range(4):
        begin = year_index * YEAR
        source = common[begin:begin + WARMUP + YEAR]
        if len(source) == WARMUP + YEAR:
            windows.append(source)
    paths = []
    for window_index, source_times in enumerate(windows):
        for replicate in range(REPLICATES):
            seed = 74000 + window_index * 100 + replicate
            item = replay_variant(build_variant(raw, source_times, seed))
            item.update({"window": window_index + 1, "replicate": replicate + 1, "seed": seed,
                         "candidate_beats_baseline": item["candidate"]["end_usd"] > item["baseline"]["end_usd"]})
            paths.append(item)
            print("path", len(paths), flush=True)
    summary = {
        "candidate_return_pct": stats(paths, "candidate", "return_pct"),
        "stress_return_pct": stats(paths, "stress", "return_pct"),
        "baseline_return_pct": stats(paths, "baseline", "return_pct"),
        "candidate_mdd_pct": stats(paths, "candidate", "close_mark_mdd_pct"),
        "profitable_candidate_years": sum(x["candidate"]["end_usd"] > 100 for x in paths),
        "profitable_stress_years": sum(x["stress"]["end_usd"] > 100 for x in paths),
        "candidate_beats_baseline_years": sum(x["candidate_beats_baseline"] for x in paths),
        "total_paths": len(paths),
    }
    per_window = []
    for index in range(1, len(windows) + 1):
        xs = [x for x in paths if x["window"] == index]
        per_window.append({"window": index, "candidate_median_return_pct": statistics.median(x["candidate"]["return_pct"] for x in xs),
                           "baseline_median_return_pct": statistics.median(x["baseline"]["return_pct"] for x in xs),
                           "candidate_profitable": sum(x["candidate"]["end_usd"] > 100 for x in xs),
                           "candidate_beats_baseline": sum(x["candidate_beats_baseline"] for x in xs)})
    result = {"id": "A-ORDERED-NOISE-STAGE74", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "candidate": "A 1.4x notional / 3x isolated / 15% emergency stop",
              "method": "Four chronological non-overlapping one-year futures windows, eight order-preserving perturbations each; weekly volatility 0.85-1.15x plus small correlated/idiosyncratic noise.",
              "summary": summary, "per_window": per_window, "paths": paths,
              "limitations": ["Perturbed historical chronology is not an independent future market.",
                              "Funding omitted; double-cost and stop-slippage stress included.",
                              "Hourly OHLC stop ordering and current BingX quantity-grid assumptions remain."]}
    out = s68.DIR.parent / "a_ordered_noise_stage74"
    out.mkdir(exist_ok=True)
    (out / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"summary": summary, "per_window": per_window}, ensure_ascii=False))


if __name__ == "__main__":
    main()

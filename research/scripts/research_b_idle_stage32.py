"""Research only: unused-symbol, one-hour supplements during Stage26 idle windows."""
import inspect, itertools, json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import research_b_sparse_stage20 as sparse

s = sparse.s
ROOT = s.core.ROOT
OUT = s.core.RESULT_DIR / "b_idle_stage32"
CURRENT_B = {"AVAX", "ICP", "BCH", "DOGE", "UNI", "ALGO", "ETH", "VET"}
PLAN_A = {"BTC", "ETH", "XRP", "TRX", "SOL"}


def compact(x):
    return {k: v for k, v in x.items() if k != "ledger"}


def weighted_replay():
    src = inspect.getsource(s.b.replay)
    src = src.replace("target*(1+x", "target*x.get('weight_scale',1.)*(1+x")
    src = src.replace("margin = target*shrink", "margin = target*shrink*x.get('weight_scale',1.)")
    env = dict(s.b.__dict__)
    exec(src, env)
    return env["replay"]


def current_stage26():
    series, entries, times = s.b.prepare()
    standard = json.loads((ROOT / "strategy/plan_b_combination_standard.json").read_text(encoding="utf8"))
    selector = standard["reference"]["selector"]
    core_busy = set()
    for t, ps in entries.items():
        for p in ps:
            core_busy.update(range(t, p["exit_bar"] + 3600000, 3600000))
    for ident in selector["patterns"]:
        symbol, pattern = ident.split(":", 1)
        rows = s.core.read_candles(s.core.DATA_DIR / f"{symbol}USDT_1h.csv")
        for row in rows:
            row["symbol"] = symbol
        series[symbol] = {r["t"]: r for r in rows}
        signal = dict(sparse.signals(rows))[pattern]
        # Stage26 supplements were selected against core idle time.
        ops = s.opportunities(rows, signal, 1, 3, core_busy)
        for op in ops:
            entries.setdefault(op["entry_ts"], []).append({**op, "weight_scale": .9 / 1.15})
    return series, entries, times, standard


def candidate_patterns(rows):
    # Causal, completed-hour rules only. No forward extrema or future labels.
    yield from sparse.signals(rows)
    o, h, l, c, v = [np.array([r[k] for r in rows]) for k in ("o", "h", "l", "c", "v")]
    span = np.maximum(h-l, 1e-12)
    lower = (np.minimum(o, c)-l)/span
    upper = (h-np.maximum(o, c))/span
    ret = np.r_[0, c[1:]/c[:-1]-1]
    avg48 = np.r_[np.full(48, np.nan), np.convolve(v, np.ones(48)/48, "valid")[:-1]]
    for n in (3, 5, 7):
        pos = np.convolve((ret > 0).astype(int), np.ones(n, dtype=int), "full")[:len(c)]
        neg = np.convolve((ret < 0).astype(int), np.ones(n, dtype=int), "full")[:len(c)]
        move = np.r_[np.zeros(n), c[n:]/c[:-n]-1]
        for shock in (.02, .03, .05):
            yield f"exhaust_n{n}_move{shock}", np.where((neg == n)&(move < -shock)&(lower > .35), 1, np.where((pos == n)&(move > shock)&(upper > .35), -1, 0))
    for shock in (.02, .03, .05):
        yield f"failed_impulse_{shock}", np.where((ret < -shock)&((c-l)/span > .65)&(v > avg48*1.25), 1, np.where((ret > shock)&((c-l)/span < .35)&(v > avg48*1.25), -1, 0))


def main():
    OUT.mkdir(exist_ok=True)
    series, entries, times, standard = current_stage26()
    run = weighted_replay()
    base = run(series, entries, times, 1.15)
    expected = standard["reference"]
    assert abs(base["return_pct"] - expected["return_pct"]) < 1e-6
    base_stress = run(series, entries, times, 1.15, cost_mult=2)
    busy = set()
    for t, ps in entries.items():
        for p in ps:
            busy.update(range(t, p["exit_bar"] + 3600000, 3600000))
    cuts = [times[0] + int((times[-1]+3600000-times[0])*k/3) for k in range(4)]
    rowsets, candidates = {}, []
    excluded = CURRENT_B | PLAN_A
    for path in sorted(s.core.DATA_DIR.glob("*USDT_1h.csv")):
        symbol = path.name.replace("USDT_1h.csv", "")
        if symbol in excluded:
            continue
        rows = s.core.read_candles(path)
        if rows[0]["t"] > times[0] or rows[-1]["t"] < times[-1]:
            continue
        for r in rows:
            r["symbol"] = symbol
        rowsets[symbol] = rows
        prefix = dict(candidate_patterns(rows[:1200]))
        for name, sig in candidate_patterns(rows):
            np.testing.assert_array_equal(sig[:1200], prefix[name])
            for lev in (2, 3):
                ops = s.opportunities(rows, sig, 1, lev, busy)
                seg = s.screen(rows, ops, cuts)
                if all(x["trades"] >= 5 for x in seg):
                    candidates.append({"id": f"{symbol}:{name}:l{lev}", "symbol": symbol, "pattern": name, "leverage": lev, "segments": seg, "score": min(x["sum_log"] for x in seg), "ops": ops})
        print("SCREEN", symbol, len(candidates), flush=True)
    nominees = [max(candidates, key=lambda x: x["segments"][k]["sum_log"]) for k in range(3)]
    ranked = sorted(candidates, key=lambda x: (x["score"], sum(z["sum_log"] for z in x["segments"])), reverse=True)
    selected = []
    for x in nominees + ranked:
        if x["id"] not in {z["id"] for z in selected} and x["symbol"] not in {z["symbol"] for z in selected}:
            selected.append(x)
        if len(selected) >= 10:
            break
    results = []
    for x in selected:
        ss = {**series, x["symbol"]: {r["t"]: r for r in rowsets[x["symbol"]]}}
        for frac in (.15, .25, .4):
            ee = {t: [dict(p) for p in ps] for t, ps in entries.items()}
            for op in x["ops"]:
                ee.setdefault(op["entry_ts"], []).append({**op, "weight_scale": frac/1.15})
            full = run(ss, ee, times, 1.15)
            stress = run(ss, ee, times, 1.15, cost_mult=2)
            segs = [compact(run(ss, ee, times, 1.15, start=cuts[k], end=cuts[k+1])) for k in range(3)]
            extra = [p for p in full["ledger"] if p["symbol"] == x["symbol"]]
            overlap = sum(any(p["entry_ts"] < q["exit_ts"] and p["exit_ts"] > q["entry_ts"] for q in full["ledger"] if q["symbol"] in CURRENT_B) for p in extra)
            assert overlap == 0
            passed = full["return_pct"] > base["return_pct"] and stress["return_pct"] > base_stress["return_pct"] and full["hourly_mark_mdd_pct"] >= -70 and not full["liquidation_proxy_count"] and not stress["liquidation_proxy_count"] and all(z["return_pct"] > 0 for z in segs)
            results.append({"id": x["id"], "target_fraction": frac, "method": x["pattern"], "symbol": x["symbol"], "leverage": x["leverage"], "full": compact(full), "double_cost": compact(stress), "segments": segs, "extra_trades": len(extra), "holding_overlap_trades": overlap, "pass": passed})
    # Small baskets: equal split of a total 40% idle budget.
    singles = sorted([r for r in results if r["target_fraction"] == .25], key=lambda x: x["full"]["return_pct"], reverse=True)
    top_ids = []
    for r in singles:
        if r["symbol"] not in {z["symbol"] for z in top_ids}:
            top_ids.append(r)
        if len(top_ids) == 4:
            break
    lookup = {x["id"]: x for x in selected}
    baskets = []
    for combo in itertools.combinations(top_ids, 2):
        ee = {t: [dict(p) for p in ps] for t, ps in entries.items()}
        ss = dict(series)
        for item in combo:
            x = lookup[item["id"]]
            ss[x["symbol"]] = {r["t"]: r for r in rowsets[x["symbol"]]}
            for op in x["ops"]:
                ee.setdefault(op["entry_ts"], []).append({**op, "weight_scale": .2/1.15})
        full = run(ss, ee, times, 1.15); stress = run(ss, ee, times, 1.15, cost_mult=2)
        segs = [compact(run(ss, ee, times, 1.15, start=cuts[k], end=cuts[k+1])) for k in range(3)]
        baskets.append({"ids": [x["id"] for x in combo], "total_target_fraction": .4, "full": compact(full), "double_cost": compact(stress), "segments": segs, "pass": full["return_pct"] > base["return_pct"] and stress["return_pct"] > base_stress["return_pct"] and full["hourly_mark_mdd_pct"] >= -70 and not full["liquidation_proxy_count"] and all(z["return_pct"] > 0 for z in segs)})
    results.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    baskets.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    output = {"id": "B-IDLE-STAGE32", "generated_at": datetime.now(timezone.utc).isoformat(), "research_only": True, "range": [s.stamp(times[0]), s.stamp(times[-1]+3600000)], "cuts": list(map(s.stamp, cuts)), "excluded_symbols": sorted(excluded), "baseline": compact(base), "baseline_double_cost": compact(base_stress), "baseline_segments": [compact(run(series, entries, times, 1.15, start=cuts[k], end=cuts[k+1])) for k in range(3)], "tested_candidates": len(candidates), "selected_candidates": len(selected), "selected_screening": [{k:v for k,v in x.items() if k != "ops"} for x in selected], "results": results, "baskets": baskets, "limitations": ["All thirds are discovery/comparison, not an independent untouched holdout", "Binance spot OHLC proxy, not BingX futures fills", "Idle is defined causally from already-selected Stage26 opportunities", "Research only; no live deployment"]}
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"baseline": compact(base), "best": results[0] if results else None, "best_basket": baskets[0] if baskets else None}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

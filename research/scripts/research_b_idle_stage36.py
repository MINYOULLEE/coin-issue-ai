"""Research only: search unused-symbol patterns in the residual idle hours of Stage35."""
import itertools
import json
from datetime import datetime, timezone

import research_b_idle_stage32 as p


s = p.s
OUT = s.core.RESULT_DIR / "b_idle_stage36"


def current_stage35():
    """Rebuild the adopted Stage35 entries without relying on the older Stage32 selector parser."""
    series, entries, times = s.b.prepare()
    standard = json.loads((p.ROOT / "strategy/plan_b_combination_standard.json").read_text(encoding="utf8"))
    core_busy = set()
    for t, positions in entries.items():
        for position in positions:
            core_busy.update(range(t, position["exit_bar"] + 3600000, 3600000))
    selectors = standard["reference"]["selector"]["patterns"]
    for selector_index, ident in enumerate(selectors):
        # Stage35's three new supplements were discovered only in the idle hours
        # left after the original Stage26 supplements had already been selected.
        if selector_index == 3:
            core_busy = set()
            for t, positions in entries.items():
                for position in positions:
                    core_busy.update(range(t, position["exit_bar"] + 3600000, 3600000))
        symbol, pattern, fraction = ident.split(":")
        rows = s.core.read_candles(s.core.DATA_DIR / f"{symbol}USDT_1h.csv")
        for row in rows:
            row["symbol"] = symbol
        series[symbol] = {r["t"]: r for r in rows}
        signal = dict(p.candidate_patterns(rows))[pattern]
        ops = s.opportunities(rows, signal, 1, int(standard["symbols"][symbol]["leverage"]), core_busy)
        for op in ops:
            entries.setdefault(op["entry_ts"], []).append({**op, "weight_scale": float(fraction) / 1.15})
    return series, entries, times, standard


def main():
    OUT.mkdir(exist_ok=True)
    series, entries, times, standard = current_stage35()
    run = p.weighted_replay()
    base = run(series, entries, times, 1.15)
    base_stress = run(series, entries, times, 1.15, cost_mult=2)
    expected = standard["reference"]
    assert standard["strategy_id"] == "b_core_idle_stage35"
    assert abs(base["return_pct"] - expected["return_pct"]) < 1e-6

    busy = set()
    for t, positions in entries.items():
        for position in positions:
            busy.update(range(t, position["exit_bar"] + 3600000, 3600000))

    cuts = [times[0] + int((times[-1] + 3600000 - times[0]) * k / 3) for k in range(4)]
    excluded = set(standard["symbols"]) | p.PLAN_A
    rowsets = {}
    candidates = []
    for path in sorted(s.core.DATA_DIR.glob("*USDT_1h.csv")):
        symbol = path.name.replace("USDT_1h.csv", "")
        if symbol in excluded:
            continue
        rows = s.core.read_candles(path)
        if rows[0]["t"] > times[0] or rows[-1]["t"] < times[-1]:
            continue
        for row in rows:
            row["symbol"] = symbol
        rowsets[symbol] = rows
        prefix = dict(p.candidate_patterns(rows[:1200]))
        for name, signal in p.candidate_patterns(rows):
            # Causality check: adding future rows cannot change the historical signal prefix.
            import numpy as np
            np.testing.assert_array_equal(signal[:1200], prefix[name])
            for leverage in (2, 3):
                ops = s.opportunities(rows, signal, 1, leverage, busy)
                segments = s.screen(rows, ops, cuts)
                if all(x["trades"] >= 4 and x["sum_log"] > 0 for x in segments):
                    candidates.append({
                        "id": f"{symbol}:{name}:l{leverage}",
                        "symbol": symbol,
                        "pattern": name,
                        "leverage": leverage,
                        "segments": segments,
                        "score": min(x["sum_log"] for x in segments),
                        "ops": ops,
                    })
        print("SCREEN", symbol, len(candidates), flush=True)

    ranked = sorted(candidates, key=lambda x: (x["score"], sum(z["sum_log"] for z in x["segments"])), reverse=True)
    selected = []
    for candidate in ranked:
        if candidate["symbol"] not in {x["symbol"] for x in selected}:
            selected.append(candidate)
        if len(selected) >= 12:
            break

    results = []
    for candidate in selected:
        symbol = candidate["symbol"]
        ss = {**series, symbol: {r["t"]: r for r in rowsets[symbol]}}
        for fraction in (.1, .15, .2, .3):
            ee = {t: [dict(x) for x in positions] for t, positions in entries.items()}
            for op in candidate["ops"]:
                ee.setdefault(op["entry_ts"], []).append({**op, "weight_scale": fraction / 1.15})
            full = run(ss, ee, times, 1.15)
            stress = run(ss, ee, times, 1.15, cost_mult=2)
            segments = [p.compact(run(ss, ee, times, 1.15, start=cuts[k], end=cuts[k + 1])) for k in range(3)]
            extra = [x for x in full["ledger"] if x["symbol"] == symbol]
            passed = (
                full["return_pct"] > base["return_pct"]
                and stress["return_pct"] > base_stress["return_pct"]
                and full["hourly_mark_mdd_pct"] >= -70
                and not full["liquidation_proxy_count"]
                and not stress["liquidation_proxy_count"]
                and all(x["return_pct"] > 0 for x in segments)
            )
            results.append({
                "id": candidate["id"], "symbol": symbol, "method": candidate["pattern"],
                "leverage": candidate["leverage"], "target_fraction": fraction,
                "extra_trades": len(extra), "full": p.compact(full),
                "double_cost": p.compact(stress), "segments": segments, "pass": passed,
            })

    # Test small two-symbol baskets using the best fraction per distinct symbol.
    best_by_symbol = []
    for symbol in {x["symbol"] for x in results}:
        best_by_symbol.append(max((x for x in results if x["symbol"] == symbol), key=lambda x: x["full"]["return_pct"]))
    best_by_symbol.sort(key=lambda x: x["full"]["return_pct"], reverse=True)
    lookup = {x["id"]: x for x in selected}
    baskets = []
    for pair in itertools.combinations(best_by_symbol[:6], 2):
        ee = {t: [dict(x) for x in positions] for t, positions in entries.items()}
        ss = dict(series)
        for item in pair:
            candidate = lookup[item["id"]]
            ss[item["symbol"]] = {r["t"]: r for r in rowsets[item["symbol"]]}
            for op in candidate["ops"]:
                ee.setdefault(op["entry_ts"], []).append({**op, "weight_scale": .15 / 1.15})
        full = run(ss, ee, times, 1.15)
        stress = run(ss, ee, times, 1.15, cost_mult=2)
        segments = [p.compact(run(ss, ee, times, 1.15, start=cuts[k], end=cuts[k + 1])) for k in range(3)]
        baskets.append({
            "ids": [x["id"] for x in pair], "fraction_each": .15,
            "full": p.compact(full), "double_cost": p.compact(stress), "segments": segments,
            "pass": full["return_pct"] > base["return_pct"] and stress["return_pct"] > base_stress["return_pct"]
                    and full["hourly_mark_mdd_pct"] >= -70 and not full["liquidation_proxy_count"]
                    and not stress["liquidation_proxy_count"] and all(x["return_pct"] > 0 for x in segments),
        })

    results.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    baskets.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    output = {
        "id": "B-IDLE-STAGE36", "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "baseline": p.compact(base), "baseline_double_cost": p.compact(base_stress),
        "cuts": list(map(s.stamp, cuts)), "excluded_symbols": sorted(excluded),
        "screened_candidates": len(candidates),
        "selected": [{k: v for k, v in x.items() if k != "ops"} for x in selected],
        "results": results, "baskets": baskets,
        "limitations": ["All thirds used for discovery/comparison", "Binance spot OHLC proxy, not BingX futures fills", "Research only; no live deployment"],
    }
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"baseline": p.compact(base), "candidates": len(candidates), "best": results[0] if results else None, "best_basket": baskets[0] if baskets else None}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

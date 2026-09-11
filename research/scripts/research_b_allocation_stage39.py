"""Research only: coordinate search of Stage35 supplement allocations."""
import json
from datetime import datetime, timezone

import research_b_idle_stage36 as p


OUT = p.s.core.RESULT_DIR / "b_allocation_stage39"
LEVELS = (0.1, 0.15, 0.3, 0.6, 0.9, 1.15)


def build():
    series, core_entries, times = p.s.b.prepare()
    standard = json.loads((p.p.ROOT / "strategy/plan_b_combination_standard.json").read_text(encoding="utf8"))
    selectors = standard["reference"]["selector"]["patterns"]
    busy = set()
    for t, positions in core_entries.items():
        for position in positions:
            busy.update(range(t, position["exit_bar"] + 3600000, 3600000))
    ops_by_symbol = {}
    for index, ident in enumerate(selectors):
        if index == 3:
            for ops in ops_by_symbol.values():
                for op in ops:
                    busy.update(range(op["entry_ts"], op["exit_bar"] + 3600000, 3600000))
        symbol, pattern, _ = ident.split(":")
        rows = p.s.core.read_candles(p.s.core.DATA_DIR / f"{symbol}USDT_1h.csv")
        for row in rows:
            row["symbol"] = symbol
        series[symbol] = {r["t"]: r for r in rows}
        sig = dict(p.p.candidate_patterns(rows))[pattern]
        ops_by_symbol[symbol] = p.s.opportunities(rows, sig, 1, int(standard["symbols"][symbol]["leverage"]), busy)
    return series, core_entries, times, standard, ops_by_symbol


def entries_for(core_entries, ops_by_symbol, weights):
    entries = {t: [dict(x) for x in positions] for t, positions in core_entries.items()}
    for symbol, ops in ops_by_symbol.items():
        for op in ops:
            entries.setdefault(op["entry_ts"], []).append({**op, "weight_scale": weights[symbol] / 1.15})
    return entries


def main():
    OUT.mkdir(exist_ok=True)
    series, core_entries, times, standard, ops = build()
    run = p.p.weighted_replay()
    current = {symbol: float(standard["symbols"][symbol]["target_margin_fraction"]) for symbol in ops}
    baseline = run(series, entries_for(core_entries, ops, current), times, 1.15)
    assert abs(baseline["return_pct"] - standard["reference"]["return_pct"]) < 1e-6
    tested = []
    weights = dict(current)
    # Coordinate search is deterministic. Each pass revisits all six signals after the other weights move.
    for _ in range(3):
        changed = False
        for symbol in ops:
            choices = []
            for level in LEVELS:
                trial = {**weights, symbol: level}
                result = run(series, entries_for(core_entries, ops, trial), times, 1.15)
                choices.append((result["return_pct"], level, result))
                tested.append({"weights": trial, "return_pct": result["return_pct"],
                               "hourly_mark_mdd_pct": result["hourly_mark_mdd_pct"]})
            _, level, _ = max((x for x in choices if x[2]["hourly_mark_mdd_pct"] >= -70 and not x[2]["liquidation_proxy_count"]), key=lambda x: x[0])
            if level != weights[symbol]:
                weights[symbol] = level
                changed = True
        if not changed:
            break
    # Fully verify the best unique trials, not only the coordinate endpoint.
    unique = {}
    for item in tested:
        key = tuple(sorted(item["weights"].items()))
        unique[key] = item
    finalists = sorted(unique.values(), key=lambda x: x["return_pct"], reverse=True)[:12]
    cuts = [times[0] + int((times[-1] + 3600000 - times[0]) * k / 3) for k in range(4)]
    verified = []
    base_stress = run(series, entries_for(core_entries, ops, current), times, 1.15, cost_mult=2)
    for item in finalists:
        ee = entries_for(core_entries, ops, item["weights"])
        full = run(series, ee, times, 1.15)
        stress = run(series, ee, times, 1.15, cost_mult=2)
        segments = [p.p.compact(run(series, ee, times, 1.15, start=cuts[k], end=cuts[k + 1])) for k in range(3)]
        verified.append({"weights": item["weights"], "full": p.p.compact(full),
                         "double_cost": p.p.compact(stress), "segments": segments,
                         "pass": full["return_pct"] > baseline["return_pct"]
                                 and stress["return_pct"] > base_stress["return_pct"]
                                 and full["hourly_mark_mdd_pct"] >= -70
                                 and not full["liquidation_proxy_count"] and not stress["liquidation_proxy_count"]
                                 and all(x["return_pct"] > 0 for x in segments)})
    verified.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    output = {"id": "B-ALLOCATION-STAGE39", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "current_weights": current, "baseline": p.p.compact(baseline),
              "baseline_double_cost": p.p.compact(base_stress), "coordinate_trials": len(tested),
              "verified": verified, "limitations": ["Same signals and historical thirds; allocation search is not independent validation", "No deployment"]}
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"trials": len(tested), "best": verified[0]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

"""Research only: re-optimize Stage35 allocations using exact deployed supplement overlap semantics."""
import json
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

import research_b_allocation_stage39 as old
import research_b_idle_stage36 as common
import report_stage39_actual_allocations as allocation_report


OUT = common.p.s.core.RESULT_DIR / "b_deployed_semantics_stage40"
LEVELS = old.LEVELS


def build():
    series, core_entries, times = common.p.s.b.prepare()
    standard = json.loads((common.p.ROOT / "strategy/plan_b_combination_standard.json").read_text(encoding="utf8"))
    core_busy = set()
    for t, positions in core_entries.items():
        for position in positions:
            core_busy.update(range(t, position["exit_bar"] + 3600000, 3600000))
    ops = {}
    for ident in standard["reference"]["selector"]["patterns"]:
        symbol, pattern, _ = ident.split(":")
        rows = common.p.s.core.read_candles(common.p.s.core.DATA_DIR / f"{symbol}USDT_1h.csv")
        for row in rows:
            row["symbol"] = symbol
        series[symbol] = {r["t"]: r for r in rows}
        signal = dict(common.p.candidate_patterns(rows))[pattern]
        # Exact deployed semantics: every supplement sees coreBusyUntil only.
        ops[symbol] = common.p.s.opportunities(rows, signal, 1, int(standard["symbols"][symbol]["leverage"]), core_busy)
    return series, core_entries, times, standard, ops


def entries_for(core_entries, ops, weights):
    entries = {t: [dict(x) for x in positions] for t, positions in core_entries.items()}
    for symbol, opportunities in ops.items():
        for op in opportunities:
            entries.setdefault(op["entry_ts"], []).append({**op, "weight_scale": weights[symbol] / 1.15})
    return entries


def compact(result):
    return {k: v for k, v in result.items() if k != "ledger"}


def allocation_summary(ledger, symbols):
    grouped = defaultdict(list)
    for row in ledger:
        if row["symbol"] in symbols:
            grouped[row["symbol"]].append(row["actual_margin_pct"])
    def stats(values):
        a = np.array(values, dtype=float)
        return {"entries": len(a), "mean_pct": float(a.mean()), "median_pct": float(np.median(a)),
                "min_pct": float(a.min()), "max_pct": float(a.max())}
    return {"symbols": {symbol: stats(grouped[symbol]) for symbol in symbols},
            "all_supplements": stats([v for symbol in symbols for v in grouped[symbol]])}


def main():
    OUT.mkdir(exist_ok=True)
    series, core_entries, times, standard, ops = build()
    run = common.p.weighted_replay()
    current = {symbol: float(standard["symbols"][symbol]["target_margin_fraction"]) for symbol in ops}
    baseline_entries = entries_for(core_entries, ops, current)
    baseline = run(series, baseline_entries, times, 1.15)
    baseline_stress = run(series, baseline_entries, times, 1.15, cost_mult=2)
    weights = dict(current)
    trials = []
    for _ in range(3):
        changed = False
        for symbol in ops:
            choices = []
            for level in LEVELS:
                trial = {**weights, symbol: level}
                result = run(series, entries_for(core_entries, ops, trial), times, 1.15)
                choices.append((result["return_pct"], level, result))
                trials.append({"weights": trial, "return_pct": result["return_pct"],
                               "hourly_mark_mdd_pct": result["hourly_mark_mdd_pct"]})
            _, level, _ = max((x for x in choices if x[2]["hourly_mark_mdd_pct"] >= -70 and not x[2]["liquidation_proxy_count"]), key=lambda x: x[0])
            if weights[symbol] != level:
                weights[symbol] = level
                changed = True
        if not changed:
            break
    unique = {tuple(sorted(x["weights"].items())): x for x in trials}
    finalists = sorted(unique.values(), key=lambda x: x["return_pct"], reverse=True)[:12]
    cuts = [times[0] + int((times[-1] + 3600000 - times[0]) * k / 3) for k in range(4)]
    verified = []
    for finalist in finalists:
        ee = entries_for(core_entries, ops, finalist["weights"])
        full = run(series, ee, times, 1.15)
        stress = run(series, ee, times, 1.15, cost_mult=2)
        segments = [compact(run(series, ee, times, 1.15, start=cuts[k], end=cuts[k + 1])) for k in range(3)]
        verified.append({"weights": finalist["weights"], "full": compact(full), "double_cost": compact(stress),
                         "segments": segments, "pass": full["return_pct"] > baseline["return_pct"]
                         and stress["return_pct"] > baseline_stress["return_pct"]
                         and full["hourly_mark_mdd_pct"] >= -70 and not full["liquidation_proxy_count"]
                         and full["hourly_adverse_bound_pct"] >= -70
                         and stress["hourly_adverse_bound_pct"] >= -70
                         and not stress["liquidation_proxy_count"] and all(x["return_pct"] > 0 for x in segments)})
    verified.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    best = verified[0]
    instrumented = allocation_report.instrumented_replay()(series, entries_for(core_entries, ops, best["weights"]), times, 1.15)
    output = {"id": "B-DEPLOYED-SEMANTICS-STAGE40", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "semantics": "all supplements gated only by coreBusyUntil; simultaneous supplements allocated proportionally",
              "opportunities": {k: len(v) for k, v in ops.items()}, "current_weights": current,
              "baseline": compact(baseline), "baseline_double_cost": compact(baseline_stress),
              "trials": len(trials), "verified": verified, "actual_allocations": allocation_summary(instrumented["ledger"], ops),
              "limitations": ["All thirds used for discovery/comparison", "Binance spot hourly proxy", "No live deployment"]}
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"baseline": output["baseline"], "baseline_double_cost": output["baseline_double_cost"],
                      "opportunities": output["opportunities"], "best": best,
                      "actual_allocations": output["actual_allocations"]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

"""Research only: safer allocation frontier under exact deployed Stage35 semantics."""
import json
from datetime import datetime, timezone

import research_b_deployed_semantics_stage40 as s40
import report_stage39_actual_allocations as allocation_report


OUT = s40.common.p.s.core.RESULT_DIR / "b_safety_stage41"
SYMBOLS = ("ALGO", "ETH", "VET", "LINK", "DOT", "LTC")


def compact(result):
    return {k: v for k, v in result.items() if k != "ledger"}


def main():
    OUT.mkdir(exist_ok=True)
    series, core_entries, times, standard, ops = s40.build()
    run = s40.common.p.weighted_replay()
    cuts = [times[0] + int((times[-1] + 3600000 - times[0]) * k / 3) for k in range(4)]

    # Stage40 showed DOT size was the cleanest risk lever. Sweep it finely while
    # also lowering the other supplements together to expose a risk/return frontier.
    common_levels = (0.75, 0.85, 0.95, 1.05, 1.15)
    dot_levels = (0.05, 0.075, 0.10, 0.125, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.60)
    trials = []
    for common_level in common_levels:
        for dot_level in dot_levels:
            weights = {symbol: common_level for symbol in SYMBOLS}
            weights["DOT"] = dot_level
            entries = s40.entries_for(core_entries, ops, weights)
            full = run(series, entries, times, 1.15)
            stress = run(series, entries, times, 1.15, cost_mult=2)
            trials.append({
                "weights": weights,
                "full": compact(full),
                "double_cost": compact(stress),
            })

    # Best return at several explicit stress-risk budgets. This avoids selecting
    # a candidate merely because it misses liquidation by a few basis points.
    frontier = {}
    for limit in (-65.0, -66.0, -67.0, -68.0):
        eligible = [x for x in trials
                    if x["full"]["hourly_adverse_bound_pct"] >= limit
                    and x["double_cost"]["hourly_adverse_bound_pct"] >= limit
                    and not x["full"]["liquidation_proxy_count"]
                    and not x["double_cost"]["liquidation_proxy_count"]]
        if eligible:
            best = max(eligible, key=lambda x: x["full"]["return_pct"])
            entries = s40.entries_for(core_entries, ops, best["weights"])
            best["segments"] = [compact(run(series, entries, times, 1.15, start=cuts[k], end=cuts[k + 1])) for k in range(3)]
            instrumented = allocation_report.instrumented_replay()(series, entries, times, 1.15)
            best["actual_allocations"] = s40.allocation_summary(instrumented["ledger"], ops)
            frontier[str(limit)] = best

    output = {
        "id": "B-SAFETY-STAGE41",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "semantics": "exact deployed Stage35 supplement overlap and proportional clipping",
        "trials": len(trials),
        "frontier": frontier,
        "limitations": ["All thirds used for discovery/comparison", "Binance spot hourly proxy", "No BingX futures or live validation", "No deployment"],
    }
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

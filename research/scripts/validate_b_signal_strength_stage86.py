"""Research only: integrate Stage85 selector candidates with current Stage66 profit locks."""
import json
from datetime import datetime, timezone

import research_b_signal_strength_stage85 as s85
import research_dynamic_targets_stage58 as s58
import research_profit_lock_stage61 as s61


OUT = s85.OUT.parent / "b_signal_strength_stage86"
CHOICES = {"ICP": (.30, .70, False), "BCH": (.70, .75, False), "UNI": (.60, .75, False)}
SHORTLIST = {
    "ALGO": {
        "capitulation_n3_move0.08_vol1.0_wick0.5",
        "capitulation_n3_move0.07_vol1.0_wick0.5",
    },
    "ETH": {"sweep_n24_excess0.015_vol1.0"},
}


def compact(result):
    return {k: v for k, v in result.items() if k != "ledger"}


def profit_lock_run(series, entries, times, features, cost_mult=1, start=None, end=None):
    exits = {}
    for symbol, (q, keep, conditional) in CHOICES.items():
        learned, _ = s61.learned_profit_locks(series, entries, features, symbol.lower(), q, keep, conditional)
        exits.update(learned)
    replay = s58.old.runner(exits)
    return replay(series, entries, times, 1.15, cost_mult=cost_mult, start=start, end=end), len(exits)


def main():
    OUT.mkdir(exist_ok=True)
    series, core_entries, times, standard, current_ops = s85.stage40.build()
    weights = {symbol: float(standard["symbols"][symbol]["target_margin_fraction"]) for symbol in current_ops}
    features = {symbol: s58.old.prev.features(list(rows.values())) for symbol, rows in series.items()}
    cuts = [times[0] + int((times[-1] + s58.H - times[0]) * k / 3) for k in range(4)]

    baseline_entries = s85.stage40.entries_for(core_entries, current_ops, weights)
    base_full, base_exits = profit_lock_run(series, baseline_entries, times, features)
    base_stress, _ = profit_lock_run(series, baseline_entries, times, features, cost_mult=2)
    baseline = {"full": compact(base_full), "double_cost": compact(base_stress), "changed_exits": base_exits}

    candidates = []
    for symbol, names in SHORTLIST.items():
        rows = [series[symbol][t] for t in sorted(series[symbol])]
        for name, signal in s85.signal_grid(symbol, rows):
            if name not in names:
                continue
            core_busy = set()
            for t, positions in core_entries.items():
                for position in positions:
                    core_busy.update(range(t, position["exit_bar"] + s58.H, s58.H))
            ops = s85.common.p.s.opportunities(rows, signal, 1, int(standard["symbols"][symbol]["leverage"]), core_busy)
            trial_ops = dict(current_ops)
            trial_ops[symbol] = ops
            entries = s85.stage40.entries_for(core_entries, trial_ops, weights)
            full, exits = profit_lock_run(series, entries, times, features)
            stress, _ = profit_lock_run(series, entries, times, features, cost_mult=2)
            segments = []
            for k in range(3):
                result, _ = profit_lock_run(series, entries, times, features, start=cuts[k], end=cuts[k + 1])
                segments.append(compact(result))
            passed = (full["return_pct"] > base_full["return_pct"]
                      and stress["return_pct"] > base_stress["return_pct"]
                      and full["hourly_mark_mdd_pct"] >= -70
                      and full["hourly_adverse_bound_pct"] >= -70
                      and stress["hourly_adverse_bound_pct"] >= -70
                      and not full["liquidation_proxy_count"]
                      and not stress["liquidation_proxy_count"]
                      and all(x["return_pct"] > 0 for x in segments))
            candidates.append({"symbol": symbol, "pattern": name, "opportunities": len(ops),
                               "changed_exits": exits, "full": compact(full),
                               "double_cost": compact(stress), "segments": segments, "pass": passed})
            print("VALIDATE", symbol, name, len(ops), round(full["return_pct"], 2), passed, flush=True)

    candidates.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    output = {"id": "B-SIGNAL-STRENGTH-STAGE86", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "live_changes": False, "baseline": baseline,
              "candidates": candidates,
              "limitations": ["Binance spot hourly proxy", "No untouched holdout",
                              "Stage65 minute-fill check covers profit-lock exits but not the newly added ALGO/ETH entries",
                              "No BingX orders and no deployment"]}
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"baseline": baseline, "best": candidates[0] if candidates else None}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

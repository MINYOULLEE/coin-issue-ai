"""Research-only: test robust Stage89 ADA session reversal as a B Stage66 supplement."""
import json
from datetime import datetime, timezone

import research_session_reversal_stage89 as s89
import validate_b_signal_strength_stage86 as s86


OUT = s89.OUT.parent / "b_ada_session_stage90"
FRACTIONS = (.05, .10, .15, .25)


def compact(x):
    return {k: v for k, v in x.items() if k != "ledger"}


def main():
    OUT.mkdir(exist_ok=True)
    series, core_entries, times, standard, current_ops = s86.s85.stage40.build()
    weights = {symbol: float(standard["symbols"][symbol]["target_margin_fraction"]) for symbol in current_ops}
    baseline_entries = s86.s85.stage40.entries_for(core_entries, current_ops, weights)
    features = {symbol: s86.s58.old.prev.features(list(rows.values())) for symbol, rows in series.items()}
    base, _ = s86.profit_lock_run(series, baseline_entries, times, features)
    base_stress, _ = s86.profit_lock_run(series, baseline_entries, times, features, cost_mult=2)
    cuts = [times[0] + int((times[-1] + s89.H - times[0]) * k / 3) for k in range(4)]

    rows = s86.s85.common.p.s.core.read_candles(s86.s85.common.p.s.core.DATA_DIR / "ADAUSDT_1h.csv")
    for row in rows:
        row["symbol"] = "ADA"
    series["ADA"] = {r["t"]: r for r in rows}
    features["ADA"] = s86.s58.old.prev.features(rows)
    sig = s89.signal_for(rows, 6, .03)
    core_busy = set()
    for t, positions in core_entries.items():
        for position in positions:
            core_busy.update(range(t, position["exit_bar"] + s89.H, s89.H))
    ops = s86.s85.common.p.s.opportunities(rows, sig, 7, 3, core_busy)

    results = []
    for fraction in FRACTIONS:
        entries = {t: [dict(x) for x in positions] for t, positions in baseline_entries.items()}
        for op in ops:
            entries.setdefault(op["entry_ts"], []).append({**op, "weight_scale": fraction / 1.15})
        full, exits = s86.profit_lock_run(series, entries, times, features)
        stress, _ = s86.profit_lock_run(series, entries, times, features, cost_mult=2)
        segments = [compact(s86.profit_lock_run(series, entries, times, features,
                    start=cuts[k], end=cuts[k + 1])[0]) for k in range(3)]
        passed = bool(full["return_pct"] > base["return_pct"]
                      and stress["return_pct"] > base_stress["return_pct"]
                      and full["hourly_mark_mdd_pct"] >= -70
                      and full["hourly_adverse_bound_pct"] >= -70
                      and stress["hourly_adverse_bound_pct"] >= -70
                      and not full["liquidation_proxy_count"] and not stress["liquidation_proxy_count"]
                      and all(x["return_pct"] > 0 for x in segments))
        results.append({"target_margin_fraction": fraction, "ada_opportunities": len(ops),
                        "changed_profit_lock_exits": exits, "full": compact(full),
                        "double_cost": compact(stress), "segments": segments, "pass": passed})
        print("FRACTION", fraction, round(full["return_pct"], 2), passed, flush=True)
    results.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    output = {"id": "B-ADA-SESSION-STAGE90", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "live_changes": False,
              "method": "ADA UTC 06/07/08 completed-hour 3% shock reversal, next-open, 7h hold, 3x",
              "baseline": {"full": compact(base), "double_cost": compact(base_stress)},
              "results": results,
              "limitations": ["Binance spot hourly proxy", "No untouched holdout",
                              "No BingX futures/minute fill validation", "No deployment"]}
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"best": results[0]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

"""Research-only: combine Stage86 ALGO relaxation and Stage90 ADA supplement."""
import json
from datetime import datetime, timezone

import validate_b_ada_session_stage90 as s90


OUT = s90.OUT.parent / "b_algo_ada_combo_stage91"


def compact(x):
    return {k: v for k, v in x.items() if k != "ledger"}


def main():
    OUT.mkdir(exist_ok=True)
    series, core_entries, times, standard, ops = s90.s86.s85.stage40.build()
    weights = {symbol: float(standard["symbols"][symbol]["target_margin_fraction"]) for symbol in ops}
    core_busy = set()
    for t, positions in core_entries.items():
        for position in positions:
            core_busy.update(range(t, position["exit_bar"] + s90.s89.H, s90.s89.H))

    algo_rows = [series["ALGO"][t] for t in sorted(series["ALGO"])]
    algo_sig = dict(s90.s86.s85.signal_grid("ALGO", algo_rows))["capitulation_n3_move0.08_vol1.0_wick0.5"]
    ops["ALGO"] = s90.s86.s85.common.p.s.opportunities(algo_rows, algo_sig, 1, 3, core_busy)

    ada_rows = s90.s86.s85.common.p.s.core.read_candles(s90.s86.s85.common.p.s.core.DATA_DIR / "ADAUSDT_1h.csv")
    for row in ada_rows:
        row["symbol"] = "ADA"
    series["ADA"] = {r["t"]: r for r in ada_rows}
    ada_sig = s90.s89.signal_for(ada_rows, 6, .03)
    ada_ops = s90.s86.s85.common.p.s.opportunities(ada_rows, ada_sig, 7, 3, core_busy)
    features = {symbol: s90.s86.s58.old.prev.features(list(rows.values())) for symbol, rows in series.items()}
    cuts = [times[0] + int((times[-1] + s90.s89.H - times[0]) * k / 3) for k in range(4)]

    results = []
    for ada_fraction in (.15, .25):
        entries = s90.s86.s85.stage40.entries_for(core_entries, ops, weights)
        for op in ada_ops:
            entries.setdefault(op["entry_ts"], []).append({**op, "weight_scale": ada_fraction / 1.15})
        full, exits = s90.s86.profit_lock_run(series, entries, times, features)
        stress, _ = s90.s86.profit_lock_run(series, entries, times, features, cost_mult=2)
        segments = [compact(s90.s86.profit_lock_run(series, entries, times, features,
                    start=cuts[k], end=cuts[k + 1])[0]) for k in range(3)]
        passed = bool(full["return_pct"] > 4_556_211.855381206
                      and stress["return_pct"] > 98_430.96285902086
                      and full["hourly_mark_mdd_pct"] >= -70
                      and full["hourly_adverse_bound_pct"] >= -70
                      and stress["hourly_adverse_bound_pct"] >= -70
                      and not full["liquidation_proxy_count"] and not stress["liquidation_proxy_count"]
                      and all(x["return_pct"] > 0 for x in segments))
        results.append({"algo_opportunities": len(ops["ALGO"]), "ada_opportunities": len(ada_ops),
                        "ada_target_margin_fraction": ada_fraction, "changed_profit_lock_exits": exits,
                        "full": compact(full), "double_cost": compact(stress), "segments": segments, "pass": passed})
    results.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    output = {"id": "B-ALGO-ADA-COMBO-STAGE91", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "live_changes": False, "results": results,
              "limitations": ["Binance spot hourly proxy", "No untouched holdout",
                              "New opportunities lack futures-minute/BingX fill validation", "No deployment"]}
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"best": results[0]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

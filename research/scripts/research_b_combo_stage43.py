"""Research only: joint DOT/BNB sizing refinement after Stage42 near miss."""
import json
from datetime import datetime, timezone

import research_b_deployed_semantics_stage40 as s40
import research_b_idle_stage32 as patterns


OUT = s40.common.p.s.core.RESULT_DIR / "b_combo_stage43"


def compact(x):
    return {k: v for k, v in x.items() if k != "ledger"}


def main():
    OUT.mkdir(exist_ok=True)
    series, core_entries, times, standard, ops = s40.build()
    run = s40.common.p.weighted_replay()
    rows = s40.common.p.s.core.read_candles(s40.common.p.s.core.DATA_DIR / "BNBUSDT_1h.csv")
    for row in rows:
        row["symbol"] = "BNB"
    series["BNB"] = {r["t"]: r for r in rows}
    core_busy = set()
    for t, positions in core_entries.items():
        for position in positions:
            core_busy.update(range(t, position["exit_bar"] + 3600000, 3600000))
    signal = dict(patterns.candidate_patterns(rows))["capitulation_n1_move0.03_vol3.0_wick0.25"]
    bnb_ops = s40.common.p.s.opportunities(rows, signal, 1, 3, core_busy)
    cuts = [times[0] + int((times[-1] + 3600000 - times[0]) * k / 3) for k in range(4)]

    trials = []
    for dot in (0.075, 0.085, 0.095, 0.10, 0.105, 0.11, 0.115, 0.12, 0.125):
        weights = {"ALGO": 1.15, "ETH": 1.15, "VET": 1.15, "LINK": 1.15, "DOT": dot, "LTC": 1.15}
        base_entries = s40.entries_for(core_entries, ops, weights)
        for bnb in (0.025, 0.04, 0.05, 0.075, 0.10, 0.125, 0.15, 0.175, 0.20):
            entries = {t: [dict(x) for x in ps] for t, ps in base_entries.items()}
            for op in bnb_ops:
                entries.setdefault(op["entry_ts"], []).append({**op, "weight_scale": bnb / 1.15})
            full = run(series, entries, times, 1.15)
            stress = run(series, entries, times, 1.15, cost_mult=2)
            ok = (full["hourly_adverse_bound_pct"] >= -67 and stress["hourly_adverse_bound_pct"] >= -67
                  and not full["liquidation_proxy_count"] and not stress["liquidation_proxy_count"])
            trials.append({"dot_request": dot, "bnb_request": bnb, "full": compact(full),
                           "double_cost": compact(stress), "safe": ok})
    safe = sorted((x for x in trials if x["safe"]), key=lambda x: x["full"]["return_pct"], reverse=True)
    frontier = {}
    for limit in (-66.5, -66.75, -66.95, -67.0):
        eligible = [x for x in trials if x["full"]["hourly_adverse_bound_pct"] >= limit
                    and x["double_cost"]["hourly_adverse_bound_pct"] >= limit]
        if eligible:
            frontier[str(limit)] = max(eligible, key=lambda x: x["full"]["return_pct"])
    # Report the best candidate with at least a small explicit buffer, if one exists.
    best = frontier.get("-66.95") or frontier["-67.0"]
    weights = {"ALGO": 1.15, "ETH": 1.15, "VET": 1.15, "LINK": 1.15,
               "DOT": best["dot_request"], "LTC": 1.15}
    entries = s40.entries_for(core_entries, ops, weights)
    for op in bnb_ops:
        entries.setdefault(op["entry_ts"], []).append({**op, "weight_scale": best["bnb_request"] / 1.15})
    best["segments"] = [compact(run(series, entries, times, 1.15, start=cuts[k], end=cuts[k + 1])) for k in range(3)]
    output = {"id": "B-COMBO-STAGE43", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "tested": len(trials), "safe_count": len(safe), "frontier": frontier,
              "bnb_rule": "BNB capitulation 1h -3%, volume>=3x, lower-wick>=25%, 3x, hold 1h",
              "bnb_opportunities": len(bnb_ops), "best": best,
              "limitations": ["All thirds used for discovery/comparison", "Binance spot hourly proxy",
                              "No independent holdout/BingX futures/live validation", "No deployment"]}
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

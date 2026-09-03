"""Research only: add unused-symbol patterns to the Stage41 safer allocation."""
import itertools
import json
from datetime import datetime, timezone

import numpy as np

import research_b_deployed_semantics_stage40 as s40
import research_b_idle_stage32 as patterns


OUT = s40.common.p.s.core.RESULT_DIR / "b_combo_stage42"
SAFE_WEIGHTS = {"ALGO": 1.15, "ETH": 1.15, "VET": 1.15,
                "LINK": 1.15, "DOT": 0.125, "LTC": 1.15}
STRESS_ADVERSE_LIMIT = -67.0


def compact(result):
    return {k: v for k, v in result.items() if k != "ledger"}


def main():
    OUT.mkdir(exist_ok=True)
    series, core_entries, times, standard, existing_ops = s40.build()
    run = s40.common.p.weighted_replay()
    base_entries = s40.entries_for(core_entries, existing_ops, SAFE_WEIGHTS)
    baseline = run(series, base_entries, times, 1.15)
    baseline_stress = run(series, base_entries, times, 1.15, cost_mult=2)

    core_busy = set()
    for t, positions in core_entries.items():
        for position in positions:
            core_busy.update(range(t, position["exit_bar"] + 3600000, 3600000))
    cuts = [times[0] + int((times[-1] + 3600000 - times[0]) * k / 3) for k in range(4)]

    excluded = set(standard["symbols"])
    rowsets, screened = {}, []
    for path in sorted(s40.common.p.s.core.DATA_DIR.glob("*USDT_1h.csv")):
        symbol = path.name.replace("USDT_1h.csv", "")
        if symbol in excluded:
            continue
        rows = s40.common.p.s.core.read_candles(path)
        if rows[0]["t"] > times[0] or rows[-1]["t"] < times[-1]:
            continue
        for row in rows:
            row["symbol"] = symbol
        rowsets[symbol] = rows
        prefix = dict(patterns.candidate_patterns(rows[:1200]))
        for name, signal in patterns.candidate_patterns(rows):
            np.testing.assert_array_equal(signal[:1200], prefix[name])
            for leverage in (2, 3):
                ops = s40.common.p.s.opportunities(rows, signal, 1, leverage, core_busy)
                thirds = s40.common.p.s.screen(rows, ops, cuts)
                if all(x["trades"] >= 4 and x["sum_log"] > 0 for x in thirds):
                    screened.append({"id": f"{symbol}:{name}:l{leverage}", "symbol": symbol,
                                     "pattern": name, "leverage": leverage, "ops": ops,
                                     "thirds": thirds, "score": min(x["sum_log"] for x in thirds)})
        print("SCREEN", symbol, len(screened), flush=True)

    # Keep multiple genuinely different patterns per symbol, then perform full
    # portfolio replay with existing supplements allowed to overlap exactly as runtime does.
    ranked = sorted(screened, key=lambda x: (x["score"], sum(z["sum_log"] for z in x["thirds"])), reverse=True)
    selected, per_symbol = [], {}
    for item in ranked:
        if per_symbol.get(item["symbol"], 0) >= 2:
            continue
        selected.append(item)
        per_symbol[item["symbol"]] = per_symbol.get(item["symbol"], 0) + 1
        if len(selected) >= 20:
            break

    singles = []
    for candidate in selected:
        symbol = candidate["symbol"]
        ss = {**series, symbol: {r["t"]: r for r in rowsets[symbol]}}
        for fraction in (0.05, 0.075, 0.10, 0.15, 0.20):
            entries = {t: [dict(x) for x in rows] for t, rows in base_entries.items()}
            for op in candidate["ops"]:
                entries.setdefault(op["entry_ts"], []).append({**op, "weight_scale": fraction / 1.15})
            full = run(ss, entries, times, 1.15)
            stress = run(ss, entries, times, 1.15, cost_mult=2)
            segments = [compact(run(ss, entries, times, 1.15, start=cuts[k], end=cuts[k + 1])) for k in range(3)]
            passed = (full["return_pct"] > baseline["return_pct"] and
                      stress["return_pct"] > baseline_stress["return_pct"] and
                      full["hourly_adverse_bound_pct"] >= STRESS_ADVERSE_LIMIT and
                      stress["hourly_adverse_bound_pct"] >= STRESS_ADVERSE_LIMIT and
                      not full["liquidation_proxy_count"] and not stress["liquidation_proxy_count"] and
                      all(x["return_pct"] > 0 for x in segments))
            singles.append({"id": candidate["id"], "symbol": symbol, "method": candidate["pattern"],
                            "leverage": candidate["leverage"], "fraction": fraction,
                            "extra_opportunities": len(candidate["ops"]), "full": compact(full),
                            "double_cost": compact(stress), "segments": segments, "pass": passed})

    singles.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    output = {"id": "B-COMBO-STAGE42", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "base_weights": SAFE_WEIGHTS, "stress_adverse_limit": STRESS_ADVERSE_LIMIT,
              "baseline": compact(baseline), "baseline_double_cost": compact(baseline_stress),
              "screened": len(screened), "selected": [{k: v for k, v in x.items() if k != "ops"} for x in selected],
              "singles": singles,
              "limitations": ["All thirds used for discovery/comparison", "Binance spot hourly proxy",
                              "No independent holdout, BingX futures, or live validation", "No deployment"]}
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"screened": len(screened), "tested": len(singles),
                      "passes": sum(x["pass"] for x in singles), "best": singles[0] if singles else None},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

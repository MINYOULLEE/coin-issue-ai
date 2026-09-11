"""Diagnose A's weak backward extension and summarize adopted B guard effects.

Research only: no credentials, live state, orders, or standards are changed.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timezone

import evaluate_ab_7y as ab
import research_a_drawdown_guard_stage75 as a75
import validate_a_exposure_scale_stage68 as a68


OUT = ab.OUT / "AB_STAGE113_REINFORCEMENT_DIAGNOSIS.json"
CUT = int(datetime(2021, 8, 28, tzinfo=timezone.utc).timestamp() * 1000)


def compact(x):
    return {k: v for k, v in x.items() if k not in ("stop_events", "ledger")}


def a_inputs():
    trees = ab.core.load_trees()
    spot = {s: ab.core.read_candles(ab.SPOT / f"{s}USDT_1h.csv") for s in a68.SYMBOLS}
    maps = {s: ab.core.targets(s, spot[s], trees[s], 0) for s in a68.SYMBOLS}
    bars, funding = {}, {}
    for symbol in a68.SYMBOLS:
        raw = json.loads((ab.FUTURES / symbol / "hours.json").read_text(encoding="utf-8"))
        bars[symbol] = {int(x[0]): {"o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4])} for x in raw}
        rates = json.loads((ab.FUTURES / symbol / "funding.json").read_text(encoding="utf-8"))
        funding[symbol] = {int(x["fundingTime"]) // ab.H * ab.H: float(x["fundingRate"]) for x in rates}
    return maps, bars, funding


def main():
    maps, bars, funding = a_inputs()
    start = min(set.intersection(*(set(bars[s]) for s in a68.SYMBOLS)))
    cfg = {"id": "guard35_075", "scale": 1.4, "dd_trigger": .35,
           "dd_reduced_scale": .75, "dd_recovery": .175}
    baseline = a75.run(maps, bars, funding, cfg, start=start, end=CUT)
    counterfactuals = []
    for symbol in a68.SYMBOLS:
        for removed_side in ("long", "short"):
            changed = copy.deepcopy(maps)
            changed[symbol] = {t: (0 if t < CUT and ((v > 0) == (removed_side == "long")) else v)
                               for t, v in changed[symbol].items()}
            result = a75.run(changed, bars, funding, cfg, start=start, end=CUT)
            counterfactuals.append({"symbol": symbol, "removed_side": removed_side,
                                    "early": compact(result),
                                    "end_usd_delta": result["end_usd"] - baseline["end_usd"],
                                    "mdd_improvement_points": result["close_mark_mdd_pct"] - baseline["close_mark_mdd_pct"]})
    b = json.loads((ab.OUT / "B_STAGE111_CAUSALITY_REPRODUCIBILITY_AUDIT.json").read_text(encoding="utf-8"))
    result = {
        "id": "AB-STAGE113-REINFORCEMENT-DIAGNOSIS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False,
        "a_early_range": [datetime.fromtimestamp(start/1000, timezone.utc).isoformat(), datetime.fromtimestamp(CUT/1000, timezone.utc).isoformat()],
        "a_early_baseline": compact(baseline),
        "a_counterfactuals": sorted(counterfactuals, key=lambda x: x["end_usd_delta"], reverse=True),
        "b_current_guard": {"causality": b["causality"], "five_year": b["five_year"], "extended": b["extended"]},
        "limitations": [
            "Removing one A symbol-side is a diagnosis, not a deployable selector.",
            "The early A window is short and starts only when all five futures histories coexist.",
            "B guard attribution remains historical and is not independent live validation.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"a_early_baseline": compact(baseline), "top": result["a_counterfactuals"][:10], "b": result["b_current_guard"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Research-only Stage76 screen: causal A scaling, stop and drawdown guards."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import research_a_drawdown_guard_stage75 as s75
import validate_a_exposure_scale_stage68 as s68
import validate_a_scale_stop_stage70 as s70

OUT = Path(__file__).resolve().parents[1] / "results" / "a_stage76_grid"
BASE_RETURN = 2_143_508.58
BASE_STRESS_RETURN = 1_033_997.04


def compact(x):
    return {k: v for k, v in x.items() if k != "ledger"}


def main():
    maps, bars, funding = s68.load()
    times = sorted(set.intersection(*[set(bars[s]) for s in s68.SYMBOLS]))
    cuts = [times[0] + int((times[-1] - times[0]) * i / 3) for i in range(4)]
    configs = []
    for scale in (1.40, 1.45, 1.50, 1.55, 1.60):
        for stop in (.12, .15, .18):
            for trigger in (.30, .35, .40, .45):
                for reduced in (.70, .80, .90, 1.00, 1.10):
                    if reduced >= scale:
                        continue
                    configs.append({"scale": scale, "stop": stop, "trigger": trigger,
                                    "reduced": reduced, "recovery": trigger / 2})
    rows = []
    for i, c in enumerate(configs, 1):
        kwargs = dict(dd_trigger=c["trigger"], dd_reduced_scale=c["reduced"], dd_recovery=c["recovery"])
        run = lambda **extra: s70.replay(maps, bars, funding, c["scale"], c["stop"], **kwargs, **extra)
        full = compact(run())
        if full["return_pct"] <= BASE_RETURN or full["close_mark_mdd_pct"] < -70:
            continue
        stress = compact(run(fee=.0008, stop_slippage=.003))
        segments = [compact(s70.replay(maps, bars, funding, c["scale"], c["stop"],
                       start=cuts[k], end=cuts[k+1], **kwargs)) for k in range(3)]
        passed = (stress["return_pct"] > BASE_STRESS_RETURN
                  and full["hourly_adverse_bound_mdd_pct"] >= -70
                  and all(x["end_usd"] > 100 and x["close_mark_mdd_pct"] >= -70 for x in segments))
        rows.append({"config": c, "full": full, "double_cost": stress,
                     "segments": segments, "screen_pass": passed})
        if i % 25 == 0:
            print("screened", i, "survivors", len(rows), flush=True)
    rows.sort(key=lambda x: x["full"]["return_pct"], reverse=True)
    result = {
        "id": "A-STAGE76-CAUSAL-GRID",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "tested": len(configs),
        "baseline": {"return_pct": BASE_RETURN, "double_cost_return_pct": BASE_STRESS_RETURN,
                     "closed_mdd_pct": -47.32, "hourly_adverse_mdd_pct": -48.36},
        "survivors": len(rows),
        "passing": [x for x in rows if x["screen_pass"]],
        "top": rows[:20],
        "limitations": ["Same historical source as Stage75", "Grid selection bias remains",
                        "Passing screen requires ordered synthetic follow-up before adoption"]
    }
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    summary = [{"config": x["config"], "return_pct": x["full"]["return_pct"],
                "stress_return_pct": x["double_cost"]["return_pct"],
                "mdd": x["full"]["close_mark_mdd_pct"],
                "adverse_mdd": x["full"]["hourly_adverse_bound_mdd_pct"],
                "order_events": x["full"]["total_order_events"], "segments": [s["return_pct"] for s in x["segments"]]}
               for x in result["passing"][:10]]
    print(json.dumps({"tested": len(configs), "passing": len(result["passing"]), "top": summary}, ensure_ascii=False))


if __name__ == "__main__":
    main()

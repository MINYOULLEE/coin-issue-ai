"""Local robustness/refinement grid around the Stage78 two-tier candidate."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import research_a_stage78_two_tier_guard as s78
import validate_a_exposure_scale_stage68 as s68

OUT = Path(__file__).resolve().parents[1] / "results" / "a_stage79_two_tier_refinement"


def main():
    maps, bars, funding = s68.load()
    times = sorted(set.intersection(*[set(bars[s]) for s in s68.SYMBOLS]))
    cuts = [times[0] + int((times[-1] - times[0]) * i / 3) for i in range(4)]
    rows = []
    tested = 0
    for t1 in (.275, .30, .325):
        for t2 in (.375, .40, .425):
            if t2 <= t1:
                continue
            for f1 in (.75, .80, .85):
                for f2 in (.45, .50, .55):
                    for recovery in (.15, .175, .20):
                        tested += 1
                        cfg = dict(scale=1.45, stop_pct=.15, t1=t1, t2=t2,
                                   f1=f1, f2=f2, recovery=recovery)
                        base = s78.replay(maps, bars, funding, **cfg)
                        double = s78.replay(maps, bars, funding, **cfg, fee=.0008, stop_slippage=.003)
                        severe = s78.replay(maps, bars, funding, **cfg, fee=.0015, stop_slippage=.01)
                        passed = (base["return_pct"] > 2_548_905.03
                                  and double["return_pct"] > 1_181_201.80
                                  and severe["end_usd"] > 100
                                  and base["max_simultaneous_adverse_margin_equity_ratio_at_3x"] <= .95
                                  and base["hourly_adverse_bound_mdd_pct"] >= -70
                                  and severe["hourly_adverse_bound_mdd_pct"] >= -70)
                        rows.append({"config": cfg, "base": base, "double": double,
                                     "severe": severe, "screen_pass": passed})
                        if tested % 25 == 0:
                            print("tested", tested, flush=True)
    preliminary = [x for x in rows if x["screen_pass"]]
    preliminary.sort(key=lambda x: x["base"]["return_pct"], reverse=True)
    passing = []
    for x in preliminary[:30]:
        cfg = x["config"]
        x["thirds"] = [s78.replay(maps, bars, funding, **cfg, start=cuts[i], end=cuts[i + 1])
                       for i in range(3)]
        if all(z["end_usd"] > 100 and z["close_mark_mdd_pct"] >= -70 for z in x["thirds"]):
            passing.append(x)
    result = {"id": "A-STAGE79-TWO-TIER-REFINEMENT", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "tested": tested, "pass_count": len(passing), "top": passing[:30],
              "limitations": ["Local grid on same five-year history", "Top candidates require synthetic follow-up"]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"tested": tested, "pass_count": len(passing), "top": [{"config": x["config"],
        "return": x["base"]["return_pct"], "double": x["double"]["return_pct"],
        "severe": x["severe"]["return_pct"], "mdd": x["base"]["close_mark_mdd_pct"],
        "adverse": x["base"]["hourly_adverse_bound_mdd_pct"],
        "margin": x["base"]["max_simultaneous_adverse_margin_equity_ratio_at_3x"],
        "events": x["base"]["total_order_events"],
        "thirds": [z["return_pct"] for z in x["thirds"]]} for x in passing[:10]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

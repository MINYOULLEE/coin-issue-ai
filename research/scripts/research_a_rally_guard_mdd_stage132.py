"""MDD-constrained refinement of the Stage130 A rally guard. Research only."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import research_a_intraday_rally_guard_stage127 as s127
import research_ab_reinforcement_stage113 as s113
import research_a_sol_short_refinement_stage115 as s115
import research_a_drawdown_guard_stage75 as s75

OUT = s115.ab.OUT / "A_STAGE132_RALLY_GUARD_MDD_REFINEMENT.json"
BASE = {"scope": "off", "btc": 9, "asset": 9, "breadth": 9, "mult": 1, "confirm": 1}


def compact(result):
    return {key: value for key, value in result.items() if key != "overlay_events"}


def configs():
    # Frozen Stage130 structure; only the nearby risk controls vary.
    for first_asset in (0.0225, 0.025, 0.0275):
        for first_mult in (0.00, 0.05, 0.10, 0.15):
            for second_asset in (0.0325, 0.035, 0.0375):
                yield {
                    "scope": "alts",
                    "btc": 0.005,
                    "asset": first_asset,
                    "breadth": 3,
                    "mult": first_mult,
                    "confirm": 2,
                    "second_btc": 0.02,
                    "second_asset": second_asset,
                    "second_breadth": 3,
                    "second_mult": 0,
                    "second_confirm": 2,
                }


def main():
    maps, bars, funding = s113.a_inputs()
    start = min(set.intersection(*(set(bars[symbol]) for symbol in s127.SYMBOLS)))
    maps = s115.filtered(maps, bars, 0.035, 0.12, 3, 0)
    baseline_five = compact(s127.replay(maps, bars, funding, BASE, s113.CUT, s127.END))
    baseline_seven = compact(s127.replay(maps, bars, funding, BASE, start, s127.END))

    screened = []
    for number, cfg in enumerate(configs(), 1):
        seven = compact(s127.replay(maps, bars, funding, cfg, start, s127.END))
        triple = compact(s127.replay(maps, bars, funding, cfg, start, s127.END, 0.0012, 0.005, 0))
        severe = compact(s127.replay(maps, bars, funding, cfg, start, s127.END, 0.0012, 0.005, 0.003))
        screened.append({"config": cfg, "seven": seven, "triple": triple, "severe": severe})
        print("screen", number, flush=True)

    # Preserve high return and historical risk first, then spend synthetic runs on finalists.
    eligible = [
        row for row in screened
        if row["seven"]["return_pct"] >= baseline_seven["return_pct"]
        and row["seven"]["hourly_adverse_bound_mdd_pct"] >= -52
        and row["triple"]["return_pct"] >= 1_000_000
    ]
    finalists = sorted(
        eligible,
        key=lambda row: (row["seven"]["return_pct"], row["severe"]["return_pct"]),
        reverse=True,
    )[:8]

    markets = list(s75.synthetic_markets())
    for finalist_number, row in enumerate(finalists, 1):
        cfg = row["config"]
        synthetic = []
        for path_number, market in enumerate(markets, 1):
            guarded_maps = s115.filtered(market["maps"], market["bars"], 0.035, 0.12, 3, 0)
            base = compact(s127.replay(guarded_maps, market["bars"], market["funding"], BASE, market["start"], market["end"]))
            candidate = compact(s127.replay(guarded_maps, market["bars"], market["funding"], cfg, market["start"], market["end"]))
            severe = compact(s127.replay(guarded_maps, market["bars"], market["funding"], cfg, market["start"], market["end"], 0.0012, 0.005, 0.003))
            synthetic.append({"path": path_number, "baseline": base, "candidate": candidate, "severe": severe})
        row["synthetic"] = {
            "paths": len(synthetic),
            "profitable": sum(item["candidate"]["end_usd"] > 100 for item in synthetic),
            "outperforms": sum(item["candidate"]["end_usd"] > item["baseline"]["end_usd"] for item in synthetic),
            "severe_profitable": sum(item["severe"]["end_usd"] > 100 for item in synthetic),
            "worst_candidate_mdd": min(item["candidate"]["hourly_adverse_bound_mdd_pct"] for item in synthetic),
            "worst_severe_mdd": min(item["severe"]["hourly_adverse_bound_mdd_pct"] for item in synthetic),
        }
        row["five"] = compact(s127.replay(maps, bars, funding, cfg, s113.CUT, s127.END))
        row["pass"] = (
            row["five"]["return_pct"] >= baseline_five["return_pct"]
            and row["synthetic"]["profitable"] == 32
            and row["synthetic"]["severe_profitable"] == 32
            and row["synthetic"]["worst_severe_mdd"] >= -70
        )
        print("finalist", finalist_number, flush=True)

    ranked = sorted(
        finalists,
        key=lambda row: (
            bool(row.get("pass")),
            row["synthetic"]["worst_severe_mdd"],
            row["seven"]["return_pct"],
        ),
        reverse=True,
    )
    result = {
        "id": "A-STAGE132-RALLY-GUARD-MDD-REFINEMENT",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_changes": False,
        "acceptance": {
            "five_year_not_below_current_A": True,
            "seven_year_not_below_current_A": True,
            "severe_return_floor_pct": 1_000_000,
            "synthetic_paths_profitable": 32,
            "synthetic_severe_paths_profitable": 32,
            "worst_synthetic_severe_mdd_floor_pct": -70,
        },
        "baseline": {"five": baseline_five, "seven": baseline_seven},
        "screened": len(screened),
        "eligible": len(eligible),
        "finalists": len(finalists),
        "passing": sum(bool(row.get("pass")) for row in ranked),
        "ranked": ranked,
        "limitations": [
            "Ordered synthetic paths are robustness tests, not future data.",
            "Minute-fill coverage remains insufficient and is not claimed by this stage.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key != "ranked"} | {"top": ranked[:3]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

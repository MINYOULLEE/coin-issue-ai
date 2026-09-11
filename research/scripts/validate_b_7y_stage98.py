"""Three-way chronological validation of Stage97 passing gross caps."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import evaluate_ab_7y as ab
import repair_b_7y_stage97 as s97


OUT = ab.OUT / "B_STAGE98_THREE_WAY_VALIDATION.json"


def compact(result):
    return {key: value for key, value in result.items() if key != "ledger"}


def main():
    series, _, times, _, _, entries, features, _ = ab.build_b_inputs()
    exits = {}
    for symbol, (quantile, keep, conditional) in ab.b91.s90.s86.CHOICES.items():
        learned, _ = ab.b91.s90.s86.s61.learned_profit_locks(
            series, entries, features, symbol.lower(), quantile, keep, conditional)
        exits.update(learned)

    start = min(times)
    end = max(times) + s97.HOUR
    span = end - start
    boundaries = [start, start + span//3, start + 2*span//3, end]
    candidates = []
    for cap in (3.0, 3.5, 4.0):
        fn = s97.runner(exits, cap)
        segments = []
        for index in range(3):
            segment = {
                "segment": index + 1,
                "start": datetime.fromtimestamp(boundaries[index]/1000, timezone.utc).isoformat(),
                "end": datetime.fromtimestamp(boundaries[index+1]/1000, timezone.utc).isoformat(),
                "base": compact(fn(series, entries, times, 1.15, start=boundaries[index], end=boundaries[index+1])),
                "double_cost": compact(fn(series, entries, times, 1.15, cost_mult=2, start=boundaries[index], end=boundaries[index+1])),
            }
            segments.append(segment)
        row = {"max_entry_gross_equity_ratio": cap, "segments": segments}
        row["all_segments_profitable"] = all(x["base"]["end_usd"] > 100 for x in segments)
        row["all_segment_base_mdd_under_70"] = all(
            x["base"]["hourly_adverse_bound_pct"] >= -70 for x in segments)
        row["all_segment_stress_mdd_under_70"] = all(
            x["double_cost"]["hourly_adverse_bound_pct"] >= -70 for x in segments)
        candidates.append(row)

    result = {
        "id": "B-STAGE98-THREE-WAY-CHRONOLOGICAL-VALIDATION",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False,
        "candidates": candidates,
        "limitations": [
            "Each segment restarts from $100, so segment returns do not multiply to the full-run result.",
            "Profit-lock thresholds and candidate parameters were selected using observed history; this is stability testing, not untouched validation.",
            "No live state, orders, switches, or adopted standards changed.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

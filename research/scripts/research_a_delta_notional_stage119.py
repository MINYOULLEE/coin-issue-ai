"""Research-only A same-direction delta-notional filter; no live changes."""
from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone

import research_ab_reinforcement_stage113 as s113
import research_a_sol_short_refinement_stage115 as s115
import research_a_cost_resilience_stage117 as s117
import validate_a_scale_stop_stage70 as s70

OUT = s115.ab.OUT / "A_STAGE119_DELTA_NOTIONAL_FILTER.json"
END = s115.END


def build_replay():
    source = inspect.getsource(s70.replay)
    source = source.replace(
        "dd_trigger=None, dd_reduced_scale=1.0, dd_recovery=None):",
        "dd_trigger=None, dd_reduced_scale=1.0, dd_recovery=None, min_delta_equity_fraction=0.0):",
    )
    source = source.replace(
        "stops = wins = allocation_actions = executed_rebalances = skipped = 0",
        "stops = wins = allocation_actions = executed_rebalances = skipped = economic_skips = 0",
    )
    needle = """            delta_notional = abs(desired - qty[s]) * bar[s][\"o\"]
            if abs(desired - qty[s]) > 1e-12:
                executed_rebalances += 1
            equity -= delta_notional * fee
            turnover += delta_notional
            qty[s] = desired
            entry[s] = bar[s][\"o\"] if desired else None"""
    replacement = """            delta_notional = abs(desired - qty[s]) * bar[s][\"o\"]
            # Never delay entries, exits or reversals. Only suppress a small resize
            # when the existing and desired positions have the same direction.
            same_direction_resize = qty[s] * desired > 0
            if same_direction_resize and delta_notional < min_delta_equity_fraction * equity:
                economic_skips += 1
                continue
            if abs(desired - qty[s]) > 1e-12:
                executed_rebalances += 1
            equity -= delta_notional * fee
            turnover += delta_notional
            qty[s] = desired
            entry[s] = bar[s][\"o\"] if desired else None"""
    if needle not in source:
        raise RuntimeError("replay patch anchor changed")
    source = source.replace(needle, replacement)
    source = source.replace(
        '"minimum_order_skips": skipped,',
        '"minimum_order_skips": skipped, "economic_resize_skips": economic_skips,',
    )
    namespace = dict(s70.__dict__)
    exec(source, namespace)
    return namespace["replay"]


REPLAY = build_replay()


def run(maps, bars, funding, start, end, threshold, fee=.0004, slip=.001):
    return REPLAY(maps, bars, funding, 1.4, .15, fee=fee, stop_slippage=slip,
                  start=start, end=end, dd_trigger=.35, dd_reduced_scale=.75,
                  dd_recovery=.175, min_delta_equity_fraction=threshold)


def compact(value):
    return {k: v for k, v in value.items() if k not in ("stop_events", "ledger")}


def main():
    maps, bars, funding = s113.a_inputs()
    start = min(set.intersection(*(set(bars[s]) for s in s115.a68.SYMBOLS)))
    guarded = s115.filtered(maps, bars, .035, .12, 3, 0)
    baseline = run(guarded, bars, funding, start, END, 0)
    rows = []
    for threshold in (.0005, .001, .0025, .005, .0075, .01, .015, .02, .03, .05):
        full = run(guarded, bars, funding, start, END, threshold)
        five = run(guarded, bars, funding, s113.CUT, END, threshold)
        double = run(guarded, bars, funding, start, END, threshold, .0008, .003)
        triple = run(guarded, bars, funding, start, END, threshold, .0012, .005)
        row = {
            "minimum_delta_pct_of_equity": threshold * 100,
            "full": compact(full), "five": compact(five),
            "double": compact(double), "triple": compact(triple),
            "order_reduction_pct": (1 - full["total_order_events"] / baseline["total_order_events"]) * 100,
        }
        row["pass"] = (five["return_pct"] >= 4_000_000 and
                       full["return_pct"] >= baseline["return_pct"] and
                       double["return_pct"] >= 2_000_000 and
                       triple["return_pct"] >= 1_000_000 and
                       full["hourly_adverse_bound_mdd_pct"] >= -55)
        rows.append(row)
        print(threshold, round(full["return_pct"], 2), round(triple["return_pct"], 2), row["pass"], flush=True)
    ranked = sorted(rows, key=lambda x: (x["pass"], x["triple"]["return_pct"], x["full"]["return_pct"]), reverse=True)
    result = {
        "id": "A-STAGE119-DELTA-NOTIONAL-FILTER",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False,
        "candidate": "Stage117 guard plus same-direction small-resize suppression",
        "baseline": compact(baseline), "screens": len(rows),
        "passing": sum(x["pass"] for x in rows), "ranked": ranked,
        "causal_rule": "At each normal A boundary, entries/exits/reversals execute immediately. A same-direction resize is skipped only when its delta notional is below the selected fraction of current equity.",
        "limitations": [
            "The threshold grid is selected on historical data and is not an independent future result.",
            "Modeled fees and stop slippage do not reproduce an order book.",
            "Historical results are not live execution validation.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passing": result["passing"], "top": ranked[:5]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

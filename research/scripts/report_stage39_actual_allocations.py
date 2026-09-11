"""Report actual post-clipping entry margin percentages for the Stage39 candidate."""
import inspect
import json
from collections import defaultdict

import numpy as np

import replay_reserved_margin_stage16 as base
import research_b_allocation_stage39 as stage


def instrumented_replay():
    source = inspect.getsource(base.replay)
    source = source.replace("target*(1+x", "target*x.get('weight_scale',1.)*(1+x")
    source = source.replace("margin = target*shrink", "margin = target*shrink*x.get('weight_scale',1.)")
    source = source.replace("entry_fee=entry_fee, funding=0.)",
                            "entry_fee=entry_fee, entry_equity=equity_open, funding=0.)")
    source = source.replace("margin=p['margin'], quantity=p['qty']",
                            "margin=p['margin'], actual_margin_pct=100*p['margin']/max(p['entry_equity'],1e-12), quantity=p['qty']")
    env = dict(base.__dict__)
    exec(source, env)
    return env["replay"]


def summary(values):
    a = np.array(values, dtype=float)
    return {"entries": len(a), "mean_pct": float(a.mean()), "median_pct": float(np.median(a)),
            "min_pct": float(a.min()), "max_pct": float(a.max()),
            "p25_pct": float(np.percentile(a, 25)), "p75_pct": float(np.percentile(a, 75))}


def main():
    series, core_entries, times, _, ops = stage.build()
    weights = {"ALGO": 1.15, "ETH": 1.15, "VET": 1.15, "LINK": 1.15, "DOT": .6, "LTC": 1.15}
    result = instrumented_replay()(series, stage.entries_for(core_entries, ops, weights), times, 1.15)
    grouped = defaultdict(list)
    for row in result["ledger"]:
        if row["symbol"] in weights:
            grouped[row["symbol"]].append(row["actual_margin_pct"])
    output = {"note": "Actual entry margin divided by entry-time equity after clipping",
              "symbols": {symbol: summary(grouped[symbol]) for symbol in weights},
              "all_supplements": summary([v for symbol in weights for v in grouped[symbol]]),
              "result": {k: v for k, v in result.items() if k != "ledger"}}
    path = stage.OUT / "actual_allocations.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

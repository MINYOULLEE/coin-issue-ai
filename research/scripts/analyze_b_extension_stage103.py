"""Diagnose the short 2021-05 to 2021-08 backward-extension regime."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

import optimize_b_delay_stage101 as s101
import repair_b_7y_stage97 as s97


OUT = s101.ab.OUT / "B_STAGE103_EXTENSION_DIAGNOSIS.json"
END = s101.START_5Y


def compact(result):
    return {key: value for key, value in result.items() if key != "ledger"}


def summarize(ledger):
    by_symbol = defaultdict(lambda: {"trades": 0, "wins": 0, "net_pnl_usd": 0.0})
    by_month = defaultdict(lambda: {"trades": 0, "wins": 0, "net_pnl_usd": 0.0})
    for row in ledger:
        month = datetime.fromtimestamp(row["exit_ts"]/1000, timezone.utc).strftime("%Y-%m")
        for bucket in (by_symbol[row["symbol"]], by_month[month]):
            bucket["trades"] += 1
            bucket["wins"] += row["net_pnl"] > 0
            bucket["net_pnl_usd"] += row["net_pnl"]
    losses = sorted(ledger, key=lambda row: row["net_pnl"])[:20]
    return {
        "by_symbol": dict(sorted(by_symbol.items(), key=lambda item: item[1]["net_pnl_usd"])),
        "by_month": dict(sorted(by_month.items())),
        "largest_losses": losses,
    }


def main():
    series, entries, times, exits = s101.delayed_inputs(1)
    start = min(times)
    candidate_fn = s97.runner(exits, 3.75, .25, 168)
    candidate = candidate_fn(series, entries, times, 1.15, start=start, end=END)
    candidate_stress = candidate_fn(series, entries, times, 1.15, cost_mult=2, start=start, end=END)
    uncapped_fn = s97.runner(exits, 99.0, .99, 0)
    uncapped = uncapped_fn(series, entries, times, 1.15, start=start, end=END)
    result = {
        "id": "B-STAGE103-EXTENSION-REGIME-DIAGNOSIS",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False,
        "range": [datetime.fromtimestamp(start/1000, timezone.utc).isoformat(),
                  datetime.fromtimestamp(END/1000, timezone.utc).isoformat()],
        "candidate": compact(candidate),
        "candidate_double_cost": compact(candidate_stress),
        "uncapped_stage93_proxy": compact(uncapped),
        "candidate_trade_diagnostics": summarize(candidate["ledger"]),
        "limitations": [
            "This is diagnosis of an observed historical regime, not a deployable date filter.",
            "Dollar PnL attribution depends on the compounded path and should not be treated as standalone symbol expectancy.",
            "No live state, orders, switches, or adopted standards changed.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

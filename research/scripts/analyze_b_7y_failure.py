"""Locate the Stage93 backward-extension drawdown and test bounded repairs."""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime, timezone

import evaluate_ab_7y as ab


OUT = ab.OUT / "B_FAILURE_ANALYSIS.json"


def compact(result):
    return {k: v for k, v in result.items() if k != "ledger"}


def run(series, entries, times, features, cost_mult=1):
    return ab.b91.s90.s86.profit_lock_run(series, entries, times, features, cost_mult=cost_mult)[0]


def trade_path(ledger):
    balance = peak = 100.0
    peak_at = None
    worst = {"drawdown_pct": 0.0}
    by_symbol = defaultdict(lambda: {"trades": 0, "net_pnl": 0.0, "wins": 0})
    by_month = defaultdict(lambda: {"trades": 0, "net_pnl": 0.0, "wins": 0})
    for row in ledger:
        balance += row["net_pnl"]
        if balance > peak:
            peak, peak_at = balance, row["exit_ts"]
        drawdown = balance / peak - 1
        if drawdown < worst["drawdown_pct"] / 100:
            worst = {"drawdown_pct": drawdown * 100, "peak_balance": peak, "trough_balance": balance,
                     "peak_at": peak_at, "trough_at": row["exit_ts"], "trough_symbol": row["symbol"]}
        month = datetime.fromtimestamp(row["exit_ts"] / 1000, timezone.utc).strftime("%Y-%m")
        for key in (row["symbol"], month):
            target = by_symbol[key] if key == row["symbol"] else by_month[key]
            target["trades"] += 1; target["net_pnl"] += row["net_pnl"]; target["wins"] += row["net_pnl"] > 0
    return worst, by_symbol, by_month


def main():
    series, core_entries, times, standard, ops, entries, features, ada_ops = ab.build_b_inputs()
    baseline = run(series, entries, times, features)
    worst, by_symbol, by_month = trade_path(baseline["ledger"])

    # Remove one signal family at a time. This is diagnosis, not a deployable proposal.
    core_symbols = {"AVAX", "ICP", "BCH", "DOGE", "UNI"}
    variants = []
    for removed in sorted(set(series) | {"NONE"}):
        trial = {t: [dict(x) for x in rows if removed == "NONE" or x["symbol"] != removed]
                 for t, rows in entries.items()}
        result = run(series, trial, times, features)
        variants.append({"removed": removed, **compact(result)})

    # Causal portfolio brakes: after a closed-trade drawdown threshold, block new
    # opportunities for a fixed number of hours. Existing trades finish normally.
    # The production engine would need an equivalent account-level state machine;
    # these are screening experiments only.
    # First screen simple exposure reductions without changing signals/exits.
    scales = []
    for factor in (.25, .40, .55, .70, .85):
        trial = {t: [{**x, "weight_scale": x.get("weight_scale", 1.0) * factor} for x in rows]
                 for t, rows in entries.items()}
        base = run(series, trial, times, features)
        stress = run(series, trial, times, features, 2)
        scales.append({"factor": factor, "base": compact(base), "double_cost": compact(stress)})

    result = {
        "id": "B-STAGE93-7Y-FAILURE-ANALYSIS", "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False,
        "baseline": compact(baseline), "ledger_drawdown_approximation": worst,
        "symbol_totals": dict(sorted(by_symbol.items(), key=lambda kv: kv[1]["net_pnl"])),
        "worst_months": dict(sorted(by_month.items(), key=lambda kv: kv[1]["net_pnl"])[:18]),
        "single_family_ablations": sorted(variants, key=lambda x: x["hourly_mark_mdd_pct"], reverse=True),
        "uniform_exposure_screens": scales,
        "core_symbols": sorted(core_symbols),
        "limitations": [
            "Ledger drawdown excludes temporary unrealized marks; authoritative MDD remains the replay hourly mark.",
            "Ablations and exposure reductions are diagnosis screens on already observed history, not adopted changes.",
            "No live state, orders, switches, or standards were changed.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({
        "baseline": result["baseline"], "ledger_worst": worst,
        "symbol_totals": result["symbol_totals"], "worst_months": result["worst_months"],
        "ablations": [{k: x[k] for k in ("removed", "return_pct", "hourly_mark_mdd_pct", "trades")} for x in result["single_family_ablations"]],
        "scales": scales,
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()

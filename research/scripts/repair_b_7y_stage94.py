"""Research-only causal repairs for the Stage93 seven-year backward failure."""
from __future__ import annotations

import inspect
import json
from collections import defaultdict
from datetime import datetime, timezone

import analyze_b_7y_failure as diagnosis


ab = diagnosis.ab
OUT = ab.OUT / "B_STAGE94_REPAIR_RESEARCH.json"
DAY = 86_400_000


def compact(result):
    return {k: v for k, v in result.items() if k != "ledger"}


def runner(exits, trigger, reduced, recovery):
    base = ab.b91.s90.s86.s58.old.prev.b
    src = inspect.getsource(base.replay)
    patches = [
        ("target*(1+x", "target*x.get('weight_scale',1.)*(1+x"),
        ("margin = target*shrink", "margin = target*shrink*x.get('weight_scale',1.)"),
        ("if proxy or t >= p['exit_bar']:", "adaptive = exits.get((s,p['entry_ts'],t))\n            if adaptive is not None and p['qty']*p['side']*(adaptive-p['entry'])-p['entry_fee']-p['funding'] > -.9*p['margin']: proxy=False\n            if proxy or adaptive is not None or t >= p['exit_bar']:"),
        ("close = bar['c']*(1-p['side']*slip)", "close = (adaptive if adaptive is not None else bar['c'])*(1-p['side']*slip)"),
        ("peak_closed = peak_mark = start_cash", "peak_closed = peak_mark = start_cash\n    guard_active = False"),
        ("equity_open = balance + unrealized('o')", "equity_open = balance + unrealized('o')\n        open_drawdown = equity_open / max(peak_mark, 1e-12) - 1\n        if not guard_active and open_drawdown <= -trigger: guard_active = True\n        elif guard_active and open_drawdown >= -recovery: guard_active = False"),
        ("target = max(equity_open, 0) * weight", "target = max(equity_open, 0) * weight * (reduced if guard_active else 1.0)"),
    ]
    for old, new in patches:
        if src.count(old) != 1:
            raise RuntimeError(f"guard replay patch mismatch: {old}")
        src = src.replace(old, new)
    env = {**base.__dict__, "exits": exits, "trigger": trigger, "reduced": reduced, "recovery": recovery}
    exec(src, env)
    return env["replay"]


def month_symbol(ledger, start="2021-05", end="2021-07"):
    out = defaultdict(lambda: {"trades": 0, "wins": 0, "net_pnl": 0.0})
    for row in ledger:
        month = datetime.fromtimestamp(row["exit_ts"] / 1000, timezone.utc).strftime("%Y-%m")
        if start <= month < end:
            item = out[f"{month}:{row['symbol']}"]
            item["trades"] += 1; item["wins"] += row["net_pnl"] > 0; item["net_pnl"] += row["net_pnl"]
    return dict(out)


def main():
    series, _, times, _, _, entries, features, _ = ab.build_b_inputs()
    baseline, exits_count = ab.b91.s90.s86.profit_lock_run(series, entries, times, features)
    exits = {}
    for symbol, (quantile, keep, conditional) in ab.b91.s90.s86.CHOICES.items():
        learned, _ = ab.b91.s90.s86.s61.learned_profit_locks(series, entries, features, symbol.lower(), quantile, keep, conditional)
        exits.update(learned)

    first = {symbol: min(rows) for symbol, rows in series.items()}
    warmups = []
    for days in (30, 60, 90, 120, 180, 270, 365):
        trial = {t: [dict(x) for x in rows if t >= first[x["symbol"]] + days * DAY] for t, rows in entries.items()}
        base, _ = ab.b91.s90.s86.profit_lock_run(series, trial, times, features)
        stress, _ = ab.b91.s90.s86.profit_lock_run(series, trial, times, features, cost_mult=2)
        warmups.append({"listing_warmup_days": days, "base": compact(base), "double_cost": compact(stress)})

    guards = []
    for trigger in (.15, .20, .25, .30, .35):
        for reduced in (.10, .25, .40, .55):
            fn = runner(exits, trigger, reduced, trigger / 2)
            base = fn(series, entries, times, 1.15)
            stress = fn(series, entries, times, 1.15, cost_mult=2)
            guards.append({"trigger_pct": trigger * 100, "reduced_scale": reduced,
                           "recovery_pct": trigger * 50, "base": compact(base), "double_cost": compact(stress)})

    def passes(row):
        b, s = row["base"], row["double_cost"]
        return b["return_pct"] >= 1_000_000 and b["hourly_mark_mdd_pct"] >= -70 \
            and b["hourly_adverse_bound_pct"] >= -70 and not b["liquidation_proxy_count"] \
            and s["hourly_mark_mdd_pct"] >= -70 and not s["liquidation_proxy_count"]
    for row in warmups + guards:
        row["pass"] = passes(row)

    result = {
        "id": "B-STAGE94-CAUSAL-REPAIR-RESEARCH", "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False, "baseline": compact(baseline),
        "baseline_profit_lock_exits": exits_count, "failure_window_by_month_symbol": month_symbol(baseline["ledger"]),
        "listing_warmup_screens": warmups, "drawdown_guard_screens": guards,
        "passing": [row for row in warmups + guards if row["pass"]],
        "limitations": ["Same backward-extension history used to design and test repairs; independent validation is still required.",
                        "No BingX orders, live switches, or adopted standards changed."],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"failure_window": result["failure_window_by_month_symbol"],
                      "warmups": warmups, "guards": guards, "passing": result["passing"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

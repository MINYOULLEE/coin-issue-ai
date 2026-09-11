"""Research-only finite shock cooldowns for the Stage93 seven-year extension."""
from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone

import evaluate_ab_7y as ab


OUT = ab.OUT / "B_STAGE95_FINITE_COOLDOWN_RESEARCH.json"
HOUR = 3_600_000


def compact(result):
    return {key: value for key, value in result.items() if key != "ledger"}


def cooldown_runner(exits, trigger, cooldown_hours):
    base = ab.b91.s90.s86.s58.old.prev.b
    src = inspect.getsource(base.replay)
    patches = [
        ("if proxy or t >= p['exit_bar']:",
         "adaptive = exits.get((s,p['entry_ts'],t))\n            if adaptive is not None and p['qty']*p['side']*(adaptive-p['entry'])-p['entry_fee']-p['funding'] > -.9*p['margin']: proxy=False\n            if proxy or adaptive is not None or t >= p['exit_bar']:"),
        ("close = bar['c']*(1-p['side']*slip)",
         "close = (adaptive if adaptive is not None else bar['c'])*(1-p['side']*slip)"),
        ("peak_closed = peak_mark = start_cash",
         "peak_closed = peak_mark = start_cash\n    risk_peak = start_cash\n    pause_until = -1\n    pause_events = 0"),
        ("equity_open = balance + unrealized('o')",
         "equity_open = balance + unrealized('o')\n        if pause_until >= 0 and t >= pause_until:\n            pause_until = -1\n            risk_peak = equity_open\n        risk_peak = max(risk_peak, equity_open)"),
        ("proposals = [x for x in entries.get(t, []) if x['exit_bar'] <= last and x['symbol'] not in positions]",
         "proposals = [x for x in entries.get(t, []) if x['exit_bar'] <= last and x['symbol'] not in positions]\n        if t < pause_until:\n            proposals = []"),
        ("mdd_mark = min(mdd_mark,mark/peak_mark-1)",
         "mdd_mark = min(mdd_mark,mark/peak_mark-1)\n        risk_peak = max(risk_peak, mark)\n        if pause_until < 0 and mark/risk_peak-1 <= -trigger:\n            pause_until = t + cooldown_hours*HOUR\n            pause_events += 1"),
        ("max_reserved_equity_ratio=max_reserved_ratio,max_gross_equity_ratio=max_gross,ledger=ledger)",
         "max_reserved_equity_ratio=max_reserved_ratio,max_gross_equity_ratio=max_gross,pause_events=pause_events,ledger=ledger)"),
    ]
    for old, new in patches:
        if src.count(old) != 1:
            raise RuntimeError(f"cooldown replay patch mismatch: {old}")
        src = src.replace(old, new)
    env = {**base.__dict__, "exits": exits, "trigger": trigger,
           "cooldown_hours": cooldown_hours, "HOUR": HOUR}
    exec(src, env)
    return env["replay"]


def main():
    series, _, times, _, _, entries, features, _ = ab.build_b_inputs()
    exits = {}
    for symbol, (quantile, keep, conditional) in ab.b91.s90.s86.CHOICES.items():
        learned, _ = ab.b91.s90.s86.s61.learned_profit_locks(
            series, entries, features, symbol.lower(), quantile, keep, conditional)
        exits.update(learned)

    screens = []
    for trigger in (.10, .15, .20, .25, .30):
        for hours in (24, 72, 168, 240, 288, 336, 360, 408, 480, 600, 720):
            fn = cooldown_runner(exits, trigger, hours)
            base = fn(series, entries, times, 1.15)
            stress = fn(series, entries, times, 1.15, cost_mult=2)
            row = {"trigger_pct": trigger*100, "cooldown_hours": hours,
                   "base": compact(base), "double_cost": compact(stress)}
            row["pass"] = (base["return_pct"] >= 1_000_000
                           and base["hourly_mark_mdd_pct"] >= -70
                           and base["hourly_adverse_bound_pct"] >= -70
                           and base["liquidation_proxy_count"] == 0
                           and stress["hourly_mark_mdd_pct"] >= -70
                           and stress["hourly_adverse_bound_pct"] >= -70
                           and stress["liquidation_proxy_count"] == 0)
            screens.append(row)

    result = {
        "id": "B-STAGE95-FINITE-SHOCK-COOLDOWN-RESEARCH",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_changes": False,
        "method": "After a causal hourly equity drawdown trigger, reject only new entries for a fixed cooldown; existing positions keep their original exits. Reset the risk peak after cooldown and resume normal sizing.",
        "screens": screens,
        "passing": [row for row in screens if row["pass"]],
        "limitations": [
            "Designed and tested on the same backward-extension sample; not independent validation.",
            "The cooldown discards opportunities rather than delaying entries.",
            "No live state, orders, switches, or adopted standards changed.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    ranked = sorted(screens, key=lambda row: (
        row["pass"], row["base"]["return_pct"], row["base"]["hourly_mark_mdd_pct"]), reverse=True)
    print(json.dumps({"passing": result["passing"], "top": ranked[:8]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

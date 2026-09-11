"""Research-only finite cooldown plus portfolio gross-entry cap for Stage93."""
from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone

import evaluate_ab_7y as ab


OUT = ab.OUT / "B_STAGE97_COOLDOWN_GROSS_CAP_RESEARCH.json"
HOUR = 3_600_000


def compact(result):
    return {key: value for key, value in result.items() if key != "ledger"}


def runner(exits, gross_cap, trigger=.30, cooldown_hours=240):
    base = ab.b91.s90.s86.s58.old.prev.b
    src = inspect.getsource(base.replay)
    patches = [
        ("peak_closed = peak_mark = start_cash",
         "peak_closed = peak_mark = start_cash\n    risk_peak = start_cash\n    pause_until = -1\n    pause_events = gross_cap_events = 0"),
        ("equity_open = balance + unrealized('o')",
         "equity_open = balance + unrealized('o')\n        if pause_until >= 0 and t >= pause_until:\n            pause_until = -1\n            risk_peak = equity_open\n        risk_peak = max(risk_peak, equity_open)"),
        ("proposals = [x for x in entries.get(t, []) if x['exit_bar'] <= last and x['symbol'] not in positions]",
         "proposals = [x for x in entries.get(t, []) if x['exit_bar'] <= last and x['symbol'] not in positions]\n        if t < pause_until:\n            proposals = []"),
        ("shrink = min(1., available/sum(demands)) if sum(demands)>0 else 0.",
         "shrink = min(1., available/sum(demands)) if sum(demands)>0 else 0.\n        existing_gross = sum(p['qty']*p['entry'] for p in positions.values())\n        proposed_gross = sum(target*x['lev'] for x in proposals)\n        gross_room = max(0., gross_cap*max(equity_open,0)-existing_gross)\n        gross_shrink = min(1., gross_room/proposed_gross) if proposed_gross>0 else 0.\n        if gross_shrink < shrink: gross_cap_events += 1\n        shrink = min(shrink, gross_shrink)"),
        ("if proxy or t >= p['exit_bar']:",
         "adaptive = exits.get((s,p['entry_ts'],t))\n            if adaptive is not None and p['qty']*p['side']*(adaptive-p['entry'])-p['entry_fee']-p['funding'] > -.9*p['margin']: proxy=False\n            if proxy or adaptive is not None or t >= p['exit_bar']:"),
        ("close = bar['c']*(1-p['side']*slip)",
         "close = (adaptive if adaptive is not None else bar['c'])*(1-p['side']*slip)"),
        ("mdd_mark = min(mdd_mark,mark/peak_mark-1)",
         "mdd_mark = min(mdd_mark,mark/peak_mark-1)\n        risk_peak = max(risk_peak, mark)\n        if pause_until < 0 and mark/risk_peak-1 <= -trigger:\n            pause_until = t + cooldown_hours*HOUR\n            pause_events += 1"),
        ("max_reserved_equity_ratio=max_reserved_ratio,max_gross_equity_ratio=max_gross,ledger=ledger)",
         "max_reserved_equity_ratio=max_reserved_ratio,max_gross_equity_ratio=max_gross,pause_events=pause_events,gross_cap_events=gross_cap_events,ledger=ledger)"),
    ]
    for old, new in patches:
        if src.count(old) != 1:
            raise RuntimeError(f"replay patch mismatch: {old}")
        src = src.replace(old, new)
    env = {**base.__dict__, "exits": exits, "gross_cap": gross_cap, "trigger": trigger,
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
    for cap in (2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0, 5.5):
        fn = runner(exits, cap)
        base = fn(series, entries, times, 1.15)
        stress = fn(series, entries, times, 1.15, cost_mult=2)
        row = {"max_entry_gross_equity_ratio": cap, "base": compact(base), "double_cost": compact(stress)}
        row["pass"] = (base["return_pct"] >= 1_000_000
                       and base["hourly_mark_mdd_pct"] >= -70
                       and base["hourly_adverse_bound_pct"] >= -70
                       and base["liquidation_proxy_count"] == 0
                       and stress["hourly_mark_mdd_pct"] >= -70
                       and stress["hourly_adverse_bound_pct"] >= -70
                       and stress["liquidation_proxy_count"] == 0)
        screens.append(row)
    result = {
        "id": "B-STAGE97-COOLDOWN-GROSS-ENTRY-CAP-RESEARCH",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False,
        "base_overlay": {"drawdown_trigger_pct": 30, "new_entry_cooldown_hours": 240},
        "screens": screens, "passing": [row for row in screens if row["pass"]],
        "limitations": [
            "The cap applies at entry and does not resize already-open quantities.",
            "Designed and tested on the same backward-extension sample; not independent validation.",
            "No live state, orders, switches, or adopted standards changed.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

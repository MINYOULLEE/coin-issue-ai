"""Research-only Stage95 cooldown plus per-position emergency stops."""
from __future__ import annotations

import inspect
import json
from datetime import datetime, timezone

import evaluate_ab_7y as ab


OUT = ab.OUT / "B_STAGE96_COOLDOWN_STOP_RESEARCH.json"
HOUR = 3_600_000


def compact(result):
    return {key: value for key, value in result.items() if key != "ledger"}


def runner(exits, stop_fraction):
    base = ab.b91.s90.s86.s58.old.prev.b
    src = inspect.getsource(base.replay)
    patches = [
        ("peak_closed = peak_mark = start_cash",
         "peak_closed = peak_mark = start_cash\n    risk_peak = start_cash\n    pause_until = -1\n    pause_events = emergency_exits = 0"),
        ("equity_open = balance + unrealized('o')",
         "equity_open = balance + unrealized('o')\n        if pause_until >= 0 and t >= pause_until:\n            pause_until = -1\n            risk_peak = equity_open\n        risk_peak = max(risk_peak, equity_open)"),
        ("proposals = [x for x in entries.get(t, []) if x['exit_bar'] <= last and x['symbol'] not in positions]",
         "proposals = [x for x in entries.get(t, []) if x['exit_bar'] <= last and x['symbol'] not in positions]\n        if t < pause_until:\n            proposals = []"),
        ("bound = balance + sum(p['qty']*p['side']*(series[s][t]['l' if p['side']>0 else 'h']-p['entry']) for s,p in positions.items())",
         "bound = balance + sum(max(p['qty']*p['side']*(series[s][t]['l' if p['side']>0 else 'h']-p['entry']), -stop_fraction*p['margin']) for s,p in positions.items())"),
        ("proxy = worst-p['entry_fee']-p['funding'] <= -.9*p['margin']",
         "proxy = worst-p['entry_fee']-p['funding'] <= -.9*p['margin']\n            emergency = worst-p['entry_fee']-p['funding'] <= -stop_fraction*p['margin']\n            adaptive = exits.get((s,p['entry_ts'],t))\n            if adaptive is not None and p['qty']*p['side']*(adaptive-p['entry'])-p['entry_fee']-p['funding'] > -.9*p['margin']: proxy=False"),
        ("if proxy or t >= p['exit_bar']:",
         "if proxy or emergency or adaptive is not None or t >= p['exit_bar']:\n                if emergency: emergency_exits += 1"),
        ("close = bar['c']*(1-p['side']*slip)",
         "close = ((p['entry']+p['side']*(-stop_fraction*p['margin']+p['entry_fee']+p['funding'])/p['qty']) if emergency else (adaptive if adaptive is not None else bar['c']))*(1-p['side']*slip)"),
        ("mdd_mark = min(mdd_mark,mark/peak_mark-1)",
         "mdd_mark = min(mdd_mark,mark/peak_mark-1)\n        risk_peak = max(risk_peak, mark)\n        if pause_until < 0 and mark/risk_peak-1 <= -.30:\n            pause_until = t + 240*HOUR\n            pause_events += 1"),
        ("max_reserved_equity_ratio=max_reserved_ratio,max_gross_equity_ratio=max_gross,ledger=ledger)",
         "max_reserved_equity_ratio=max_reserved_ratio,max_gross_equity_ratio=max_gross,pause_events=pause_events,emergency_exits=emergency_exits,ledger=ledger)"),
    ]
    for old, new in patches:
        if src.count(old) != 1:
            raise RuntimeError(f"replay patch mismatch: {old}")
        src = src.replace(old, new)
    env = {**base.__dict__, "exits": exits, "stop_fraction": stop_fraction, "HOUR": HOUR}
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
    for stop in (.40, .50, .60, .65, .70, .75, .80):
        fn = runner(exits, stop)
        base = fn(series, entries, times, 1.15)
        stress = fn(series, entries, times, 1.15, cost_mult=2)
        row = {"margin_loss_stop_fraction": stop, "base": compact(base), "double_cost": compact(stress)}
        row["pass"] = (base["return_pct"] >= 1_000_000
                       and base["hourly_mark_mdd_pct"] >= -70
                       and base["hourly_adverse_bound_pct"] >= -70
                       and base["liquidation_proxy_count"] == 0
                       and stress["hourly_mark_mdd_pct"] >= -70
                       and stress["hourly_adverse_bound_pct"] >= -70
                       and stress["liquidation_proxy_count"] == 0)
        screens.append(row)
    result = {
        "id": "B-STAGE96-COOLDOWN-EMERGENCY-STOP-RESEARCH",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False,
        "base_overlay": {"drawdown_trigger_pct": 30, "new_entry_cooldown_hours": 240},
        "screens": screens, "passing": [row for row in screens if row["pass"]],
        "limitations": [
            "Hourly OHLC assumes a stop can fill at its threshold plus configured slippage; one-minute/gap validation is required.",
            "Designed and tested on the same backward-extension sample; not independent validation.",
            "No live state, orders, switches, or adopted standards changed.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

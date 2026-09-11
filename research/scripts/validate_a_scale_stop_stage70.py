"""A 1.5x sizing + 3x isolated leverage emergency-stop validation (research only)."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone

import validate_a_exposure_scale_stage68 as s68


RULES = {"BTC": (4, .0001, 2), "ETH": (2, .01, 2), "XRP": (0, 2, 2), "SOL": (2, .02, 2), "TRX": (0, 7, 2)}
H = s68.H


def rounded_qty(symbol, signed_notional, price):
    precision, minimum, min_usdt = RULES[symbol]
    step = 10 ** (-precision)
    amount = math.floor((abs(signed_notional) / price + 1e-12) / step) * step
    if amount < minimum - 1e-12 or amount * price < min_usdt:
        return 0.0
    return math.copysign(amount, signed_notional)


def replay(maps, bars, funding, scale, stop_pct, fee=.0004, stop_slippage=.001, start=None, end=None,
           dd_trigger=None, dd_reduced_scale=1.0, dd_recovery=None):
    common = sorted(set.intersection(*(set(bars[s]) for s in s68.SYMBOLS)))
    if start is not None:
        common = [t for t in common if t >= start]
    if end is not None:
        common = [t for t in common if t < end]
    equity = peak = 100.0
    qty = {s: 0.0 for s in s68.SYMBOLS}
    entry = {s: None for s in s68.SYMBOLS}
    stops = wins = allocation_actions = executed_rebalances = skipped = 0
    stop_events = []
    turnover = funding_paid = 0.0
    close_mdd = adverse_mdd = 0.0
    max_gross_equity = max_margin_equity = max_adverse_margin_equity = 0.0
    guard_active = False
    guard_activations = guard_decision_boundaries = 0
    for i, t in enumerate(common):
        bar = {s: bars[s][t] for s in s68.SYMBOLS}
        # Mark the previous position through any open gap before resizing.
        if i:
            prev_t = common[i - 1]
            for s in s68.SYMBOLS:
                equity += qty[s] * (bar[s]["o"] - bars[s][prev_t]["c"])
        if equity <= 0:
            break
        drawdown = equity / max(peak, 1e-12) - 1
        if dd_trigger is not None:
            recovery = dd_recovery if dd_recovery is not None else dd_trigger / 2
            if not guard_active and drawdown <= -abs(dd_trigger):
                guard_active = True
                guard_activations += 1
            elif guard_active and drawdown >= -abs(recovery):
                guard_active = False
        # A's completed daily signal is reconciled at this execution boundary.
        for s in s68.SYMBOLS:
            if t not in maps[s]:
                continue
            allocation_actions += 1
            effective_scale = scale * (dd_reduced_scale if guard_active else 1.0)
            desired = rounded_qty(s, maps[s][t] * effective_scale * equity, bar[s]["o"])
            if guard_active:
                guard_decision_boundaries += 1
            if maps[s][t] and not desired:
                skipped += 1
            delta_notional = abs(desired - qty[s]) * bar[s]["o"]
            if abs(desired - qty[s]) > 1e-12:
                executed_rebalances += 1
            equity -= delta_notional * fee
            turnover += delta_notional
            qty[s] = desired
            entry[s] = bar[s]["o"] if desired else None
        # Conservative simultaneous hourly adverse mark before close/stop handling.
        adverse_equity = equity
        open_gross = sum(abs(qty[s]) * bar[s]["o"] for s in s68.SYMBOLS)
        max_gross_equity = max(max_gross_equity, open_gross / max(equity, 1e-12))
        max_margin_equity = max(max_margin_equity, open_gross / 3 / max(equity, 1e-12))
        for s in s68.SYMBOLS:
            q = qty[s]
            if q:
                adverse_equity += q * ((bar[s]["l"] - bar[s]["o"]) if q > 0 else (bar[s]["h"] - bar[s]["o"]))
        adverse_mdd = min(adverse_mdd, adverse_equity / peak - 1)
        adverse_gross = sum(abs(qty[s]) * (bar[s]["l"] if qty[s] > 0 else bar[s]["h"]) for s in s68.SYMBOLS if qty[s])
        max_adverse_margin_equity = max(max_adverse_margin_equity, adverse_gross / 3 / max(adverse_equity, 1e-12))
        for s in s68.SYMBOLS:
            q = qty[s]
            if not q:
                continue
            e = entry[s]
            hit = (q > 0 and bar[s]["l"] <= e * (1 - stop_pct)) or (q < 0 and bar[s]["h"] >= e * (1 + stop_pct))
            if hit:
                base_fill = e * (1 - stop_pct) if q > 0 else e * (1 + stop_pct)
                fill = base_fill * (1 - stop_slippage) if q > 0 else base_fill * (1 + stop_slippage)
                pnl = q * (fill - bar[s]["o"])
                equity += pnl - abs(q) * fill * fee
                turnover += abs(q) * fill
                stops += 1
                stop_events.append({"time": t, "symbol": s, "side": "long" if q > 0 else "short",
                                    "entry": e, "threshold": base_fill, "modeled_fill": fill,
                                    "hour_open": bar[s]["o"], "hour_high": bar[s]["h"], "hour_low": bar[s]["l"]})
                wins += pnl > 0
                qty[s] = 0.0
                entry[s] = None
            else:
                equity += q * (bar[s]["c"] - bar[s]["o"])
                rate = funding[s].get(t, 0.0)
                payment = q * bar[s]["c"] * rate
                equity -= payment
                funding_paid += payment
        peak = max(peak, equity)
        close_mdd = min(close_mdd, equity / peak - 1)
    return {
        "start_usd": 100,
        "end_usd": equity,
        "return_pct": equity - 100,
        "close_mark_mdd_pct": close_mdd * 100,
        "hourly_adverse_bound_mdd_pct": adverse_mdd * 100,
        "allocation_actions": allocation_actions,
        "executed_rebalance_orders": executed_rebalances,
        "total_order_events": executed_rebalances + stops,
        "emergency_stop_exits": stops,
        "stop_events": stop_events,
        "minimum_order_skips": skipped,
        "turnover_usd": turnover,
        "funding_paid_usd": funding_paid,
        "max_open_gross_equity_ratio": max_gross_equity,
        "max_open_required_margin_equity_ratio_at_3x": max_margin_equity,
        "max_simultaneous_adverse_margin_equity_ratio_at_3x": max_adverse_margin_equity,
        "drawdown_guard": {"trigger": dd_trigger, "reduced_scale": dd_reduced_scale,
                           "recovery": dd_recovery, "activations": guard_activations,
                           "guarded_symbol_decisions": guard_decision_boundaries},
    }


def main():
    maps, bars, funding = s68.load()
    times = sorted(set.intersection(*(set(bars[s]) for s in s68.SYMBOLS)))
    lo, hi = times[0], times[-1] + H
    cuts = [lo + (hi - lo) * k // 3 for k in range(4)]
    rows = []
    for scale in (1.0, 1.2, 1.3, 1.4, 1.5):
        for stop in (.10, .15, .20, .25, .30):
            base = replay(maps, bars, funding, scale, stop)
            stressed = replay(maps, bars, funding, scale, stop, fee=.0008, stop_slippage=.003)
            thirds = [replay(maps, bars, funding, scale, stop, start=cuts[k], end=cuts[k + 1]) for k in range(3)]
            safety = []
            for leverage in (3, 4, 5):
                liq_distance = 95 / leverage
                safety.append({
                    "exchange_leverage": leverage,
                    "approx_liquidation_distance_pct": liq_distance,
                    "stop_to_liquidation_buffer_pct_points": liq_distance - stop * 100,
                    "max_open_required_margin_equity_pct": base["max_open_gross_equity_ratio"] / leverage * 100,
                    "max_simultaneous_adverse_margin_equity_pct": base["max_simultaneous_adverse_margin_equity_ratio_at_3x"] * 3 / leverage * 100,
                })
            rows.append({"scale": scale, "stop_pct": stop * 100, "leverage_safety": safety,
                         "base": base, "double_cost_and_3x_stop_slippage": stressed, "thirds": thirds})
    result = {
        "id": "A-SCALE-STOP-STAGE70", "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "range": ["2021-08-28", "2026-08-29"], "rows": rows,
        "contract_rules": RULES,
        "method": "Binance USD-M hourly futures/funding; daily causal A target; current BingX quantity grid; stop then wait for next daily signal.",
        "limitations": ["Hourly OHLC cannot resolve cross-symbol intrahour ordering.",
                        "Stop fill assumes threshold plus stated slippage, not order-book depth.",
                        "Current BingX contract grid is applied historically; historical grid is unverified.",
                        "Signal trees are not an untouched holdout; no live change was made."],
    }
    out = s68.DIR.parent / "a_scale_stop_stage70"
    out.mkdir(exist_ok=True)
    (out / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

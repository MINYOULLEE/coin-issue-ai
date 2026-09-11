"""Research only: causal two-tier drawdown guard for A; no live changes."""
from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path

import validate_a_exposure_scale_stage68 as s68
import validate_a_scale_stop_stage70 as s70

OUT = Path(__file__).resolve().parents[1] / "results" / "a_stage78_two_tier_guard"
BASE_RETURN = 2_548_905.03
BASE_DOUBLE = 1_181_201.80
H = s68.H


def replay(maps, bars, funding, scale, stop_pct, t1, t2, f1, f2, recovery,
           fee=.0004, stop_slippage=.001, start=None, end=None, scale_overlay=None,
           overlay_min_drawdown=None):
    common = sorted(set.intersection(*(set(bars[s]) for s in s68.SYMBOLS)))
    if start is not None:
        common = [t for t in common if t >= start]
    if end is not None:
        common = [t for t in common if t < end]
    equity = peak = 100.0
    qty = {s: 0.0 for s in s68.SYMBOLS}
    entry = {s: None for s in s68.SYMBOLS}
    close_mdd = adverse_mdd = 0.0
    max_margin = max_adverse_margin = max_gross = 0.0
    executed = stops = actions = skipped = 0
    turnover = funding_paid = 0.0
    level = 0
    level_counts = {"0": 0, "1": 0, "2": 0}
    for i, t in enumerate(common):
        bar = {s: bars[s][t] for s in s68.SYMBOLS}
        if i:
            prev = common[i - 1]
            for s in s68.SYMBOLS:
                equity += qty[s] * (bar[s]["o"] - bars[s][prev]["c"])
        if equity <= 0:
            break
        dd = equity / max(peak, 1e-12) - 1
        if dd <= -t2:
            level = 2
        elif dd <= -t1:
            level = 1
        elif dd >= -recovery:
            level = 0
        # Between recovery and t1 retain the prior level (hysteresis).
        factor = (1.0, f1, f2)[level]
        overlay = 1.0 if scale_overlay is None else scale_overlay.get(t, 1.0)
        if overlay_min_drawdown is not None and dd > -abs(overlay_min_drawdown):
            overlay = 1.0
        for s in s68.SYMBOLS:
            if t not in maps[s]:
                continue
            actions += 1
            level_counts[str(level)] += 1
            symbol_overlay = overlay.get(s, 1.0) if isinstance(overlay, dict) else overlay
            desired = s70.rounded_qty(s, maps[s][t] * scale * factor * symbol_overlay * equity, bar[s]["o"])
            if maps[s][t] and not desired:
                skipped += 1
            delta = abs(desired - qty[s]) * bar[s]["o"]
            if abs(desired - qty[s]) > 1e-12:
                executed += 1
            equity -= delta * fee
            turnover += delta
            qty[s] = desired
            entry[s] = bar[s]["o"] if desired else None
        adverse_equity = equity
        gross = sum(abs(qty[s]) * bar[s]["o"] for s in s68.SYMBOLS)
        max_gross = max(max_gross, gross / max(equity, 1e-12))
        max_margin = max(max_margin, gross / 3 / max(equity, 1e-12))
        for s in s68.SYMBOLS:
            q = qty[s]
            if q:
                adverse_equity += q * ((bar[s]["l"] - bar[s]["o"]) if q > 0 else (bar[s]["h"] - bar[s]["o"]))
        adverse_mdd = min(adverse_mdd, adverse_equity / peak - 1)
        adverse_gross = sum(abs(qty[s]) * (bar[s]["l"] if qty[s] > 0 else bar[s]["h"])
                            for s in s68.SYMBOLS if qty[s])
        max_adverse_margin = max(max_adverse_margin, adverse_gross / 3 / max(adverse_equity, 1e-12))
        for s in s68.SYMBOLS:
            q = qty[s]
            if not q:
                continue
            e = entry[s]
            hit = (q > 0 and bar[s]["l"] <= e * (1 - stop_pct)) or (q < 0 and bar[s]["h"] >= e * (1 + stop_pct))
            if hit:
                base_fill = e * (1 - stop_pct) if q > 0 else e * (1 + stop_pct)
                fill = base_fill * (1 - stop_slippage) if q > 0 else base_fill * (1 + stop_slippage)
                equity += q * (fill - bar[s]["o"]) - abs(q) * fill * fee
                turnover += abs(q) * fill
                qty[s] = 0.0
                entry[s] = None
                stops += 1
            else:
                equity += q * (bar[s]["c"] - bar[s]["o"])
                payment = q * bar[s]["c"] * funding[s].get(t, 0.0)
                equity -= payment
                funding_paid += payment
        peak = max(peak, equity)
        close_mdd = min(close_mdd, equity / peak - 1)
    return {
        "start_usd": 100.0, "end_usd": equity, "return_pct": equity - 100,
        "close_mark_mdd_pct": close_mdd * 100,
        "hourly_adverse_bound_mdd_pct": adverse_mdd * 100,
        "allocation_actions": actions, "executed_rebalance_orders": executed,
        "total_order_events": executed + stops, "emergency_stop_exits": stops,
        "minimum_order_skips": skipped, "turnover_usd": turnover,
        "funding_paid_usd": funding_paid, "max_open_gross_equity_ratio": max_gross,
        "max_open_required_margin_equity_ratio_at_3x": max_margin,
        "max_simultaneous_adverse_margin_equity_ratio_at_3x": max_adverse_margin,
        "guard": {"t1": t1, "t2": t2, "f1": f1, "f2": f2,
                  "recovery": recovery, "decision_counts": level_counts},
    }


def compact(x):
    return x


def main():
    maps, bars, funding = s68.load()
    times = sorted(set.intersection(*[set(bars[s]) for s in s68.SYMBOLS]))
    cuts = [times[0] + int((times[-1] - times[0]) * i / 3) for i in range(4)]
    rows = []
    for t1 in (.20, .25, .30):
        for t2 in (.35, .40, .45):
            if t2 <= t1:
                continue
            for f1 in (.70, .80, .90):
                for f2 in (.35, .40, .50):
                    for recovery in (.10, .15, .175):
                        cfg = dict(scale=1.45, stop_pct=.15, t1=t1, t2=t2,
                                   f1=f1, f2=f2, recovery=recovery)
                        base = replay(maps, bars, funding, **cfg)
                        if base["return_pct"] <= BASE_RETURN or base["max_simultaneous_adverse_margin_equity_ratio_at_3x"] > .95:
                            continue
                        double = replay(maps, bars, funding, **cfg, fee=.0008, stop_slippage=.003)
                        severe = replay(maps, bars, funding, **cfg, fee=.0015, stop_slippage=.01)
                        thirds = [replay(maps, bars, funding, **cfg, start=cuts[i], end=cuts[i + 1]) for i in range(3)]
                        passed = (double["return_pct"] > BASE_DOUBLE and severe["end_usd"] > 100
                                  and severe["hourly_adverse_bound_mdd_pct"] >= -70
                                  and all(x["end_usd"] > 100 and x["close_mark_mdd_pct"] >= -70 for x in thirds))
                        rows.append({"config": cfg, "base": base, "double": double,
                                     "severe": severe, "thirds": thirds, "screen_pass": passed})
                        print("candidate", len(rows), round(base["return_pct"], 2), passed, flush=True)
    rows.sort(key=lambda x: x["base"]["return_pct"], reverse=True)
    result = {"id": "A-STAGE78-TWO-TIER-GUARD", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "tested": 243, "passing": [x for x in rows if x["screen_pass"]],
              "top": rows[:20], "baseline": "A Stage77 corrected guard candidate",
              "limitations": ["Same historical signal source", "Grid-selected, not an independent holdout",
                              "Synthetic ordered-path follow-up required"]}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"passing": len(result["passing"]), "top": [{"config": x["config"],
        "return": x["base"]["return_pct"], "double": x["double"]["return_pct"],
        "severe": x["severe"]["return_pct"], "mdd": x["base"]["close_mark_mdd_pct"],
        "adverse": x["base"]["hourly_adverse_bound_mdd_pct"],
        "margin": x["base"]["max_simultaneous_adverse_margin_equity_ratio_at_3x"],
        "events": x["base"]["total_order_events"],
        "thirds": [z["return_pct"] for z in x["thirds"]]} for x in result["passing"][:10]]}, ensure_ascii=False))


if __name__ == "__main__":
    main()

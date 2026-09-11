"""Research-only causal profit-lock exits for current B Stage45.

The lock arms only after a completed candle closes beyond a learned favorable
excursion threshold.  The resulting stop is active from the next candle, so
the replay does not use an unknown intrabar ordering.
"""
import json
from datetime import datetime, timezone

import numpy as np
import research_dynamic_targets_stage58 as s58

OUT = s58.OUT.parent / "profit_lock_stage61"
RULES = [(scope, q, keep) for scope in ("all", "uni") for q in (.30, .50, .65, .80) for keep in (.25, .50, .75)]


def compact(result):
    return {k: v for k, v in result.items() if k != "ledger"}


def learned_profit_locks(series, entries, features, scope, quantile, keep_fraction, conditional=False):
    samples = s58.old.samples(series, entries, features)
    exits, decisions = {}, []
    for cur in samples:
        symbol, entry_ts, side = cur["symbol"], cur["t"], cur["side"]
        eligible = scope == "all" or symbol == scope.upper()
        history = s58.old.select_history(samples, cur, conditional) if eligible else []
        decision = {
            "symbol": symbol, "entry_ts": entry_ts, "eligible": eligible,
            "training_winners": len(history), "active": bool(history),
            "latest_training_close": max((x["known_at"] for x in history), default=None),
        }
        if not history:
            decisions.append(decision)
            continue
        assert decision["latest_training_close"] <= entry_ts
        raw = series[symbol][entry_ts]["o"]
        atr = features[symbol][entry_ts]["atr"]
        trigger_distance = float(np.quantile([x["mfe"] for x in history], quantile)) * atr
        armed = False
        stop = None
        peak_close_distance = 0.0
        for bar_ts in range(entry_ts, cur["exit_bar"] + s58.H, s58.H):
            bar = series[symbol][bar_ts]
            if armed:
                price, reason, ambiguous = s58.old.prev.hit(bar, stop, None, side)
                if price is not None:
                    exits[(symbol, entry_ts, bar_ts)] = float(price)
                    decision.update(exit_bar=bar_ts, reason="profit_lock", ambiguous=ambiguous, exit_price=float(price))
                    break
            favorable_close = side * (bar["c"] - raw)
            peak_close_distance = max(peak_close_distance, favorable_close)
            if peak_close_distance >= trigger_distance:
                armed = True
                candidate = raw + side * peak_close_distance * keep_fraction
                stop = max(stop, candidate) if side > 0 and stop is not None else min(stop, candidate) if side < 0 and stop is not None else candidate
        decision.update(armed=armed, trigger_distance=trigger_distance, keep_fraction=keep_fraction, final_stop=stop)
        decisions.append(decision)
    return exits, decisions


def main():
    OUT.mkdir(exist_ok=True)
    series, core_entries, times, standard, opportunities = s58.current.s40.build()
    weights = {symbol: float(standard["symbols"][symbol]["target_margin_fraction"]) for symbol in opportunities}
    entries = s58.current.s40.entries_for(core_entries, opportunities, weights)
    features = {symbol: s58.old.prev.features(list(rows.values())) for symbol, rows in series.items()}
    cuts = [times[0] + int((times[-1] + s58.H - times[0]) * k / 3) for k in range(4)]

    baseline_replay = s58.old.runner({})
    run_base = lambda **kw: baseline_replay(series, entries, times, 1.15, **kw)
    base = {
        "rule": "baseline", "full": compact(run_base()), "double_cost": compact(run_base(cost_mult=2)),
        "segments": [compact(run_base(start=cuts[k], end=cuts[k + 1])) for k in range(3)],
        "armed": 0, "exits": 0,
    }
    results = [base]
    for scope, quantile, keep_fraction in RULES:
        name = f"{scope}_q{int(quantile * 100)}_keep{int(keep_fraction * 100)}"
        exits, decisions = learned_profit_locks(series, entries, features, scope, quantile, keep_fraction)
        replay = s58.old.runner(exits)
        run = lambda **kw: replay(series, entries, times, 1.15, **kw)
        item = {
            "rule": name, "scope": scope, "trigger_quantile": quantile, "keep_fraction": keep_fraction,
            "full": compact(run()), "double_cost": compact(run(cost_mult=2)),
            "segments": [compact(run(start=cuts[k], end=cuts[k + 1])) for k in range(3)],
            "armed": sum(bool(x.get("armed")) for x in decisions), "exits": len(exits),
            "ambiguous": sum(bool(x.get("ambiguous")) for x in decisions),
        }
        results.append(item)
        print(name, json.dumps(item["full"]), flush=True)

    for item in results:
        item["robust_pass"] = bool(
            item["rule"] != "baseline"
            and item["full"]["return_pct"] > base["full"]["return_pct"]
            and item["double_cost"]["return_pct"] > base["double_cost"]["return_pct"]
            and item["full"]["hourly_mark_mdd_pct"] >= base["full"]["hourly_mark_mdd_pct"]
            and item["full"]["liquidation_proxy_count"] == 0
            and item["double_cost"]["liquidation_proxy_count"] == 0
            and all(item["segments"][i]["return_pct"] >= base["segments"][i]["return_pct"] for i in range(3))
        )
    output = {
        "id": "B-PROFIT-LOCK-STAGE61", "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "runtime_id": standard["strategy_id"], "start_usd": 100,
        "definition": "Causal prior-winner MFE/ATR quantile arms after a completed close; from the next candle, retain 25/50/75% of the best favorable close excursion. Original time exit remains the fallback.",
        "results": results,
        "limitations": ["Binance spot hourly proxy", "All three partitions were previously exposed to research", "No BingX futures/tick execution", "No live changes"],
    }
    (OUT / "RESULTS.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    ranked = sorted(results[1:], key=lambda x: x["full"]["return_pct"], reverse=True)
    print(json.dumps({"baseline": base, "best": ranked[0], "robust": [x["rule"] for x in ranked if x["robust_pass"]]}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

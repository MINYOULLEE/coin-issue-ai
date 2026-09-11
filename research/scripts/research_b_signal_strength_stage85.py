"""Research only: test whether current B supplement signals are unnecessarily strict.

This does not modify strategy standards, Supabase, switches, or live execution.
Candidates replace exactly one deployed supplement selector and are evaluated with
the same reserved-margin portfolio replay, three chronological thirds, and 2x cost.
"""
import json
from datetime import datetime, timezone

import numpy as np

import research_b_deployed_semantics_stage40 as stage40


common = stage40.common
OUT = common.p.s.core.RESULT_DIR / "b_signal_strength_stage85"


def signal_grid(symbol, rows):
    o, h, l, c, v = [np.array([r[k] for r in rows]) for k in ("o", "h", "l", "c", "v")]
    span = np.maximum(h - l, 1e-12)
    lower = (np.minimum(o, c) - l) / span
    upper = (h - np.maximum(o, c)) / span
    avg48 = np.r_[np.full(48, np.nan), np.convolve(v, np.ones(48) / 48, "valid")[:-1]]

    def capit(n, shock, vol, wick):
        move = np.r_[np.zeros(n), c[n:] / c[:-n] - 1]
        return np.where((move < -shock) & (lower > wick) & (v > avg48 * vol), 1,
                        np.where((move > shock) & (upper > wick) & (v > avg48 * vol), -1, 0))

    def sweep(n, excess, vol):
        lows = np.r_[np.full(n, np.nan), np.min(np.lib.stride_tricks.sliding_window_view(l, n), axis=1)[:-1]]
        highs = np.r_[np.full(n, np.nan), np.max(np.lib.stride_tricks.sliding_window_view(h, n), axis=1)[:-1]]
        return np.where((l < lows * (1 - excess)) & (c > lows) & (lower > .4) & (v > avg48 * vol), 1,
                        np.where((h > highs * (1 + excess)) & (c < highs) & (upper > .4) & (v > avg48 * vol), -1, 0))

    def exhaust(n, shock, wick):
        ret = np.r_[0, c[1:] / c[:-1] - 1]
        pos = np.convolve((ret > 0).astype(int), np.ones(n, dtype=int), "full")[:len(c)]
        neg = np.convolve((ret < 0).astype(int), np.ones(n, dtype=int), "full")[:len(c)]
        move = np.r_[np.zeros(n), c[n:] / c[:-n] - 1]
        return np.where((neg == n) & (move < -shock) & (lower > wick), 1,
                        np.where((pos == n) & (move > shock) & (upper > wick), -1, 0))

    if symbol == "ALGO":
        for shock in (.04, .05, .06, .07, .08):
            for vol in (1., 1.25, 1.5):
                for wick in (.35, .5):
                    yield f"capitulation_n3_move{shock}_vol{vol}_wick{wick}", capit(3, shock, vol, wick)
    elif symbol == "ETH":
        for excess in (.005, .01, .015):
            for vol in (1., 1.25, 1.5):
                yield f"sweep_n24_excess{excess}_vol{vol}", sweep(24, excess, vol)
    elif symbol == "VET":
        for excess in (.01, .02, .03):
            for vol in (1.5, 2., 2.5, 3.):
                yield f"sweep_n24_excess{excess}_vol{vol}", sweep(24, excess, vol)
    elif symbol == "LINK":
        for shock in (.03, .04, .05):
            for wick in (.25, .35):
                yield f"exhaust_n3_move{shock}_wick{wick}", exhaust(3, shock, wick)
    elif symbol == "DOT":
        for shock in (.03, .04, .05):
            for vol in (1., 1.5, 2., 3.):
                for wick in (.35, .5):
                    yield f"capitulation_n12_move{shock}_vol{vol}_wick{wick}", capit(12, shock, vol, wick)
    elif symbol == "LTC":
        for shock in (.03, .04, .05):
            for wick in (.25, .35):
                yield f"exhaust_n5_move{shock}_wick{wick}", exhaust(5, shock, wick)
    elif symbol == "BNB":
        for shock in (.02, .025, .03):
            for vol in (1.5, 2., 2.5, 3.):
                for wick in (.15, .25):
                    yield f"capitulation_n1_move{shock}_vol{vol}_wick{wick}", capit(1, shock, vol, wick)


def compact(result):
    return {k: v for k, v in result.items() if k != "ledger"}


def main():
    OUT.mkdir(exist_ok=True)
    series, core_entries, times, standard, current_ops = stage40.build()
    run = common.p.weighted_replay()
    weights = {symbol: float(standard["symbols"][symbol]["target_margin_fraction"]) for symbol in current_ops}
    baseline_entries = stage40.entries_for(core_entries, current_ops, weights)
    baseline = run(series, baseline_entries, times, 1.15)
    baseline_stress = run(series, baseline_entries, times, 1.15, cost_mult=2)
    cuts = [times[0] + int((times[-1] + 3600000 - times[0]) * k / 3) for k in range(4)]

    core_busy = set()
    for t, positions in core_entries.items():
        for position in positions:
            core_busy.update(range(t, position["exit_bar"] + 3600000, 3600000))

    screens = []
    nominees = []
    for symbol in current_ops:
        rows = common.p.s.core.read_candles(common.p.s.core.DATA_DIR / f"{symbol}USDT_1h.csv")
        for row in rows:
            row["symbol"] = symbol
        variants = []
        for name, signal in signal_grid(symbol, rows):
            ops = common.p.s.opportunities(rows, signal, 1, int(standard["symbols"][symbol]["leverage"]), core_busy)
            segments = common.p.s.screen(rows, ops, cuts)
            item = {"symbol": symbol, "pattern": name, "opportunities": len(ops),
                    "segments": segments, "score": min(x["sum_log"] for x in segments), "ops": ops}
            variants.append(item)
            screens.append({k: v for k, v in item.items() if k != "ops"})
        # Replay a small evidence-balanced shortlist, not every data-mined variant.
        eligible = [x for x in variants if all(z["trades"] >= 4 and z["sum_log"] > 0 for z in x["segments"])]
        top = sorted(eligible, key=lambda x: (x["score"], sum(z["sum_log"] for z in x["segments"])), reverse=True)[:4]
        nominees.extend(top)
        print("SCREEN", symbol, "variants", len(variants), "eligible", len(eligible), "top", len(top), flush=True)

    verified = []
    for candidate in nominees:
        trial_ops = dict(current_ops)
        trial_ops[candidate["symbol"]] = candidate["ops"]
        entries = stage40.entries_for(core_entries, trial_ops, weights)
        full = run(series, entries, times, 1.15)
        stress = run(series, entries, times, 1.15, cost_mult=2)
        segments = [compact(run(series, entries, times, 1.15, start=cuts[k], end=cuts[k + 1])) for k in range(3)]
        passed = (full["return_pct"] > baseline["return_pct"]
                  and stress["return_pct"] > baseline_stress["return_pct"]
                  and full["hourly_mark_mdd_pct"] >= -70
                  and full["hourly_adverse_bound_pct"] >= -70
                  and stress["hourly_adverse_bound_pct"] >= -70
                  and not full["liquidation_proxy_count"]
                  and not stress["liquidation_proxy_count"]
                  and all(x["return_pct"] > 0 for x in segments))
        verified.append({"symbol": candidate["symbol"], "pattern": candidate["pattern"],
                         "opportunities": candidate["opportunities"], "full": compact(full),
                         "double_cost": compact(stress), "segments": segments, "pass": passed})
        print("REPLAY", candidate["symbol"], candidate["pattern"], candidate["opportunities"],
              round(full["return_pct"], 2), passed, flush=True)

    verified.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    output = {
        "id": "B-SIGNAL-STRENGTH-STAGE85", "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False,
        "baseline": compact(baseline), "baseline_double_cost": compact(baseline_stress),
        "current_opportunities": {k: len(v) for k, v in current_ops.items()},
        "screened_variants": len(screens), "screens": screens, "verified": verified,
        "limitations": [
            "Supplement selectors only; core AVAX/ICP/BCH/DOGE/UNI unchanged",
            "Stage45 entry/exit portfolio replay; Stage66 minute profit-lock must be revalidated before adoption",
            "Binance spot hourly proxy, not BingX futures fills",
            "All thirds used for robustness comparison; no untouched holdout",
            "No deployment or live-state change",
        ],
    }
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"baseline": output["baseline"], "current_opportunities": output["current_opportunities"],
                      "screened_variants": output["screened_variants"],
                      "passing": sum(x["pass"] for x in verified), "best": verified[0] if verified else None},
                     ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

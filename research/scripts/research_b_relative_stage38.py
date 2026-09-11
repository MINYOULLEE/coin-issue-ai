"""Research only: BTC-relative spread and dislocation reversals in Stage35 idle hours."""
import json
from datetime import datetime, timezone

import numpy as np

import research_b_idle_stage36 as p


OUT = p.s.core.RESULT_DIR / "b_relative_stage38"


def prior_stats(values, window):
    mean = np.full(len(values), np.nan)
    std = np.full(len(values), np.nan)
    windows = np.lib.stride_tricks.sliding_window_view(values[:-1], window)
    mean[window:] = windows.mean(axis=1)
    std[window:] = windows.std(axis=1)
    return mean, np.maximum(std, 1e-12)


def patterns(rows, btc):
    o, h, l, c, v = [np.array([r[k] for r in rows]) for k in ("o", "h", "l", "c", "v")]
    bc = np.array([btc[r["t"]]["c"] for r in rows])
    span = np.maximum(h - l, 1e-12)
    lower = (np.minimum(o, c) - l) / span
    upper = (h - np.maximum(o, c)) / span
    avg48 = np.r_[np.full(48, np.nan), np.convolve(v, np.ones(48) / 48, "valid")[:-1]]
    ratio = np.log(c / bc)
    for window in (24, 72, 168):
        mean, std = prior_stats(ratio, window)
        z = (ratio - mean) / std
        for edge in (1.5, 2, 2.5, 3):
            for volume in (1, 1.5):
                yield f"spread_z_w{window}_e{edge}_v{volume}", np.where(
                    (z < -edge) & (lower > .25) & (v > avg48 * volume), 1,
                    np.where((z > edge) & (upper > .25) & (v > avg48 * volume), -1, 0))
    for window in (3, 12, 24):
        coin_move = np.r_[np.zeros(window), c[window:] / c[:-window] - 1]
        btc_move = np.r_[np.zeros(window), bc[window:] / bc[:-window] - 1]
        relative = coin_move - btc_move
        for edge in (.02, .03, .05):
            for volume in (1, 1.5):
                yield f"relative_move_w{window}_e{edge}_v{volume}", np.where(
                    (relative < -edge) & (lower > .25) & (v > avg48 * volume), 1,
                    np.where((relative > edge) & (upper > .25) & (v > avg48 * volume), -1, 0))


def main():
    OUT.mkdir(exist_ok=True)
    series, entries, times, standard = p.current_stage35()
    run = p.p.weighted_replay()
    base = run(series, entries, times, 1.15)
    stress_base = run(series, entries, times, 1.15, cost_mult=2)
    busy = set()
    for t, positions in entries.items():
        for position in positions:
            busy.update(range(t, position["exit_bar"] + 3600000, 3600000))
    cuts = [times[0] + int((times[-1] + 3600000 - times[0]) * k / 3) for k in range(4)]
    btc_rows = p.s.core.read_candles(p.s.core.DATA_DIR / "BTCUSDT_1h.csv")
    btc = {r["t"]: r for r in btc_rows}
    excluded = set(standard["symbols"]) | p.p.PLAN_A
    rowsets, candidates = {}, []
    for path in sorted(p.s.core.DATA_DIR.glob("*USDT_1h.csv")):
        symbol = path.name.replace("USDT_1h.csv", "")
        if symbol in excluded:
            continue
        rows = p.s.core.read_candles(path)
        if rows[0]["t"] > times[0] or rows[-1]["t"] < times[-1] or any(r["t"] not in btc for r in rows):
            continue
        for row in rows:
            row["symbol"] = symbol
        rowsets[symbol] = rows
        prefix = dict(patterns(rows[:1200], btc))
        for name, signal in patterns(rows, btc):
            np.testing.assert_array_equal(signal[:1200], prefix[name])
            for leverage in (2, 3):
                ops = p.s.opportunities(rows, signal, 1, leverage, busy)
                segments = p.s.screen(rows, ops, cuts)
                if all(x["trades"] >= 5 and x["sum_log"] > 0 for x in segments):
                    candidates.append({"id": f"{symbol}:{name}:l{leverage}", "symbol": symbol,
                                       "method": name, "leverage": leverage, "ops": ops,
                                       "segments": segments, "score": min(x["sum_log"] for x in segments)})
        print("SCREEN", symbol, len(candidates), flush=True)
    ranked = sorted(candidates, key=lambda x: (x["score"], sum(y["sum_log"] for y in x["segments"])), reverse=True)
    selected = []
    for candidate in ranked:
        if candidate["symbol"] not in {x["symbol"] for x in selected}:
            selected.append(candidate)
        if len(selected) >= 10:
            break
    results = []
    for candidate in selected:
        ss = {**series, candidate["symbol"]: {r["t"]: r for r in rowsets[candidate["symbol"]]}}
        for fraction in (.1, .2, .3, .4):
            ee = {t: [dict(x) for x in positions] for t, positions in entries.items()}
            for op in candidate["ops"]:
                ee.setdefault(op["entry_ts"], []).append({**op, "weight_scale": fraction / 1.15})
            full = run(ss, ee, times, 1.15)
            stress = run(ss, ee, times, 1.15, cost_mult=2)
            segments = [p.p.compact(run(ss, ee, times, 1.15, start=cuts[k], end=cuts[k + 1])) for k in range(3)]
            results.append({"id": candidate["id"], "symbol": candidate["symbol"], "method": candidate["method"],
                            "leverage": candidate["leverage"], "target_fraction": fraction,
                            "extra_trades": len(candidate["ops"]), "full": p.p.compact(full),
                            "double_cost": p.p.compact(stress), "segments": segments,
                            "pass": full["return_pct"] > base["return_pct"] and stress["return_pct"] > stress_base["return_pct"]
                                    and full["hourly_mark_mdd_pct"] >= -70 and not full["liquidation_proxy_count"]
                                    and not stress["liquidation_proxy_count"] and all(x["return_pct"] > 0 for x in segments)})
    results.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    output = {"id": "B-RELATIVE-STAGE38", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "baseline": p.p.compact(base), "baseline_double_cost": p.p.compact(stress_base),
              "screened": len(candidates), "selected": [{k: v for k, v in x.items() if k != "ops"} for x in selected],
              "results": results, "limitations": ["All thirds used for discovery/comparison", "BTC-relative rules use Binance spot OHLC", "No deployment"]}
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"screened": len(candidates), "passed": sum(x["pass"] for x in results), "best": results[0] if results else None}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

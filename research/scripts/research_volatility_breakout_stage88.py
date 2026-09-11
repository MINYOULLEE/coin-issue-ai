"""Research-only causal volatility-compression breakout study."""
import itertools
import json
from datetime import datetime, timezone

import numpy as np

import replay_mdd30 as core


OUT = core.RESULT_DIR / "volatility_breakout_stage88"
SYMBOLS = ("ADA", "ATOM", "FIL", "XLM", "AAVE", "ETC")
H = 3_600_000


def rolling_prior(a, n, reducer):
    out = np.full(len(a), np.nan)
    if len(a) > n:
        view = np.lib.stride_tricks.sliding_window_view(a, n)
        out[n:] = reducer(view[:-1], axis=1)
    return out


def signals(rows, vol_window, compress_q, breakout_window, volume_mult):
    h = np.array([r["h"] for r in rows]); l = np.array([r["l"] for r in rows])
    c = np.array([r["c"] for r in rows]); v = np.array([r["v"] for r in rows])
    ret = np.r_[0.0, np.diff(np.log(c))]
    sigma = rolling_prior(ret, vol_window, np.std)
    # Causal percentile threshold: only the preceding 720 completed measurements.
    threshold = np.full(len(c), np.nan)
    for i in range(720 + vol_window, len(c)):
        history = sigma[i - 720:i]
        threshold[i] = np.nanquantile(history, compress_q)
    prior_high = rolling_prior(h, breakout_window, np.max)
    prior_low = rolling_prior(l, breakout_window, np.min)
    avg_volume = rolling_prior(v, 48, np.mean)
    compressed = sigma <= threshold
    return np.where(compressed & (c > prior_high) & (v >= avg_volume * volume_mult), 1,
                    np.where(compressed & (c < prior_low) & (v >= avg_volume * volume_mult), -1, 0))


def simulate(rows, signal, hold, leverage, start, end, cost_mult=1.0):
    t = np.array([r["t"] for r in rows], dtype=np.int64)
    o = np.array([r["o"] for r in rows]); c = np.array([r["c"] for r in rows])
    i = max(1, int(np.searchsorted(t, start))); stop = int(np.searchsorted(t, end))
    equity = 1.0; peak = 1.0; mdd = 0.0; trades = 0; bisc = 0; next_i = i
    while i + hold < stop:
        if i < next_i or signal[i] == 0 or t[i + 1] - t[i] != H:
            i += 1; continue
        entry_i = i + 1; exit_i = entry_i + hold
        if t[exit_i] - t[entry_i] != hold * H:
            i += 1; continue
        side = float(signal[i])
        entry = o[entry_i] * (1 + side * .0002)
        exit_price = c[exit_i] * (1 - side * .0002)
        hours = hold + 1
        net = leverage * (side * (exit_price / entry - 1)
                          - (.0005 * 2 + .0000125 * hours) * cost_mult)
        equity *= max(.001, 1 + net); peak = max(peak, equity); mdd = min(mdd, equity / peak - 1)
        trades += 1; bisc += net > 0; next_i = exit_i + 1; i = next_i
    return {"start_usd": 100.0, "end_usd": equity * 100, "return_pct": (equity - 1) * 100,
            "max_drawdown_pct": mdd * 100, "trades": trades,
            "win_rate_pct": bisc / trades * 100 if trades else 0.0}


def main():
    OUT.mkdir(exist_ok=True)
    results = []
    for symbol in SYMBOLS:
        rows = core.read_candles(core.DATA_DIR / f"{symbol}USDT_1h.csv")
        times = np.array([r["t"] for r in rows], dtype=np.int64)
        cuts = [int(times[0] + (times[-1] + H - times[0]) * k / 3) for k in range(4)]
        grid = []
        for vw, q, bw, vm in itertools.product((24, 72), (.10, .20, .30), (24, 72), (1.0, 1.5)):
            sig = signals(rows, vw, q, bw, vm)
            for hold, lev in itertools.product((3, 6, 12, 24), (1.0, 2.0, 3.0)):
                seg = [simulate(rows, sig, hold, lev, cuts[k], cuts[k + 1]) for k in range(3)]
                grid.append({"volatility_window": vw, "compression_quantile": q,
                             "breakout_window": bw, "volume_multiple": vm,
                             "hold_hours": hold, "leverage": lev, "segments": seg})
        nominees = []
        for origin in range(3):
            eligible = [x for x in grid if x["segments"][origin]["trades"] >= 8]
            best = max(eligible, key=lambda x: np.log(max(.001, x["segments"][origin]["end_usd"] / 100))
                       + x["segments"][origin]["max_drawdown_pct"] / 50)
            if best not in nominees:
                nominees.append(best)
        for rule in nominees:
            sig = signals(rows, rule["volatility_window"], rule["compression_quantile"],
                          rule["breakout_window"], rule["volume_multiple"])
            seg = [simulate(rows, sig, rule["hold_hours"], rule["leverage"], cuts[k], cuts[k + 1]) for k in range(3)]
            full = simulate(rows, sig, rule["hold_hours"], rule["leverage"], cuts[0], cuts[3])
            stress = simulate(rows, sig, rule["hold_hours"], rule["leverage"], cuts[0], cuts[3], 2.0)
            passed = bool(all(x["return_pct"] > 0 and x["trades"] >= 8 and x["max_drawdown_pct"] >= -50 for x in seg)
                      and full["return_pct"] > 0 and full["max_drawdown_pct"] >= -50
                      and stress["return_pct"] > 0 and stress["max_drawdown_pct"] >= -60)
            results.append({"symbol": symbol, **{k: v for k, v in rule.items() if k != "segments"},
                            "segments": seg, "full": full, "double_cost": stress, "pass": passed})
        print("SYMBOL", symbol, "nominees", len(nominees), "pass", sum(x["pass"] for x in results if x["symbol"] == symbol), flush=True)
    results.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    output = {"id": "VOLATILITY-BREAKOUT-STAGE88", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "live_changes": False,
              "method": "causal low-volatility compression followed by completed-hour range breakout; next-open entry",
              "grid_per_symbol": 288, "results": results,
              "limitations": ["Binance spot hourly proxy", "No order-book/BingX fill validation",
                              "Each third nominates rules; no untouched holdout", "No deployment"]}
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"passing": sum(x["pass"] for x in results), "best": results[0] if results else None}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

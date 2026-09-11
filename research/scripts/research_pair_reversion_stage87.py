"""Research-only causal market-neutral pair-reversion search.

Each rule is selected on one chronological third and then replayed unchanged on
all three thirds. Entries occur at the next hourly open after a completed-hour
z-score signal. No live state, standards, database, or orders are modified.
"""
import itertools
import json
from datetime import datetime, timezone

import numpy as np

import replay_mdd30 as core


OUT = core.RESULT_DIR / "pair_reversion_stage87"
SYMBOLS = ("ADA", "ATOM", "FIL", "XLM", "AAVE", "ETC")
WINDOWS = (72, 168, 336, 720)
ENTRIES = (1.5, 2.0, 2.5, 3.0)
EXITS = (0.0, 0.5, 1.0)
MAX_HOLDS = (6, 12, 24, 48)
GROSS_LEVERAGES = (1.0, 2.0, 3.0)
ONE_HOUR = 3_600_000


def aligned(a, b):
    aa = {r["t"]: r for r in core.read_candles(core.DATA_DIR / f"{a}USDT_1h.csv")}
    bb = {r["t"]: r for r in core.read_candles(core.DATA_DIR / f"{b}USDT_1h.csv")}
    ts = np.array(sorted(set(aa) & set(bb)), dtype=np.int64)
    # Require a continuous five-year-like hourly span; gaps are handled by refusing entries across them.
    oa = np.array([aa[int(t)]["o"] for t in ts]); ca = np.array([aa[int(t)]["c"] for t in ts])
    ob = np.array([bb[int(t)]["o"] for t in ts]); cb = np.array([bb[int(t)]["c"] for t in ts])
    return ts, oa, ca, ob, cb


def zscore(log_ratio, window):
    out = np.full(len(log_ratio), np.nan)
    if len(log_ratio) <= window:
        return out
    view = np.lib.stride_tricks.sliding_window_view(log_ratio, window)
    means = view.mean(axis=1); stds = view.std(axis=1)
    # Window ending at i-1: the completed signal value at i is compared only with prior history.
    out[window:] = (log_ratio[window:] - means[:-1]) / np.maximum(stds[:-1], 1e-12)
    return out


def simulate(ts, oa, ca, ob, cb, z, entry_z, exit_z, max_hold, gross_lev,
             start, end, cost_mult=1.0):
    equity = 1.0; peak = 1.0; mdd = 0.0; trades = 0; wins = 0
    i = max(1, int(np.searchsorted(ts, start)))
    stop = int(np.searchsorted(ts, end))
    round_trip_cost = gross_lev * (.0005 + .0002) * 2 * cost_mult
    while i + 1 < stop:
        if not np.isfinite(z[i]) or abs(z[i]) < entry_z or ts[i + 1] - ts[i] != ONE_HOUR:
            i += 1; continue
        # Positive ratio z: short A, long B. Negative z: long A, short B.
        side_a = -1.0 if z[i] > 0 else 1.0
        entry_i = i + 1; exit_i = None
        for j in range(entry_i, min(entry_i + max_hold, stop - 1)):
            if ts[j + 1] - ts[j] != ONE_HOUR:
                break
            if np.isfinite(z[j]) and abs(z[j]) <= exit_z:
                exit_i = j + 1; break
        if exit_i is None:
            exit_i = min(entry_i + max_hold, stop - 1)
        if exit_i <= entry_i or ts[exit_i] - ts[entry_i] != (exit_i - entry_i) * ONE_HOUR:
            i = max(i + 1, exit_i); continue
        ra = side_a * (oa[exit_i] / oa[entry_i] - 1)
        rb = -side_a * (ob[exit_i] / ob[entry_i] - 1)
        net = gross_lev * .5 * (ra + rb) - round_trip_cost
        equity *= max(.001, 1 + net)
        peak = max(peak, equity); mdd = min(mdd, equity / peak - 1)
        trades += 1; wins += net > 0
        i = exit_i + 1
    return {"start_usd": 100.0, "end_usd": equity * 100,
            "return_pct": (equity - 1) * 100, "max_drawdown_pct": mdd * 100,
            "trades": trades, "win_rate_pct": wins / trades * 100 if trades else 0.0}


def main():
    OUT.mkdir(exist_ok=True)
    all_results = []
    for a, b in itertools.combinations(SYMBOLS, 2):
        ts, oa, ca, ob, cb = aligned(a, b)
        ratio = np.log(ca / cb)
        cuts = [int(ts[0] + (ts[-1] + ONE_HOUR - ts[0]) * k / 3) for k in range(4)]
        grid = []
        for window in WINDOWS:
            z = zscore(ratio, window)
            for entry_z, exit_z, hold, lev in itertools.product(ENTRIES, EXITS, MAX_HOLDS, GROSS_LEVERAGES):
                segments = [simulate(ts, oa, ca, ob, cb, z, entry_z, exit_z, hold, lev,
                                     cuts[k], cuts[k + 1]) for k in range(3)]
                grid.append({"window": window, "entry_z": entry_z, "exit_z": exit_z,
                             "max_hold_hours": hold, "gross_leverage": lev, "segments": segments})
        nominees = []
        for origin in range(3):
            eligible = [x for x in grid if x["segments"][origin]["trades"] >= 8]
            best = max(eligible, key=lambda x: (np.log(max(.001, x["segments"][origin]["end_usd"] / 100))
                                                + x["segments"][origin]["max_drawdown_pct"] / 50))
            if best not in nominees:
                nominees.append(best)
        pair_results = []
        for rule in nominees:
            z = zscore(ratio, rule["window"])
            segments = [simulate(ts, oa, ca, ob, cb, z, rule["entry_z"], rule["exit_z"],
                                 rule["max_hold_hours"], rule["gross_leverage"], cuts[k], cuts[k + 1]) for k in range(3)]
            full = simulate(ts, oa, ca, ob, cb, z, rule["entry_z"], rule["exit_z"],
                            rule["max_hold_hours"], rule["gross_leverage"], cuts[0], cuts[3])
            stress = simulate(ts, oa, ca, ob, cb, z, rule["entry_z"], rule["exit_z"],
                              rule["max_hold_hours"], rule["gross_leverage"], cuts[0], cuts[3], 2.0)
            passed = (all(x["return_pct"] > 0 and x["trades"] >= 8 and x["max_drawdown_pct"] >= -50 for x in segments)
                      and full["return_pct"] > 0 and full["max_drawdown_pct"] >= -50
                      and stress["return_pct"] > 0 and stress["max_drawdown_pct"] >= -60)
            pair_results.append({"pair": f"{a}/{b}", **{k: v for k, v in rule.items() if k != "segments"},
                                 "segments": segments, "full": full, "double_cost": stress, "pass": passed})
        all_results.extend(pair_results)
        print("PAIR", a, b, "nominees", len(pair_results), "pass", sum(x["pass"] for x in pair_results), flush=True)
    all_results.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    output = {"id": "PAIR-REVERSION-STAGE87", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "live_changes": False, "symbols": SYMBOLS,
              "method": "causal next-open market-neutral log-price-ratio z-score reversion",
              "tested_grid_per_pair": len(WINDOWS) * len(ENTRIES) * len(EXITS) * len(MAX_HOLDS) * len(GROSS_LEVERAGES),
              "results": all_results,
              "limitations": ["Binance spot hourly proxy", "Pair legs assume equal-notional simultaneous fills",
                              "No funding, borrow, order-book depth, or BingX fill validation",
                              "Each third nominates rules; no untouched holdout", "No deployment"]}
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"tested_pairs": 15, "passing": sum(x["pass"] for x in all_results),
                      "best": all_results[0] if all_results else None}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

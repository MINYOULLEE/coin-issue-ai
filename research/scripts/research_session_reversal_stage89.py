"""Research-only causal UTC-session shock-reversal search on unused symbols."""
import itertools
import json
from datetime import datetime, timezone

import numpy as np

import replay_mdd30 as core


OUT = core.RESULT_DIR / "session_reversal_stage89"
SYMBOLS = ("ADA", "ATOM", "FIL", "XLM", "AAVE", "ETC")
SESSION_STARTS = tuple(range(0, 24, 3))
SHOCKS = (.01, .015, .02, .03, .05)
HOLDS = (1, 2, 4, 7)
LEVERAGES = (1.0, 2.0, 3.0)
H = 3_600_000


def signal_for(rows, session_start, shock):
    t = np.array([r["t"] for r in rows], dtype=np.int64)
    o = np.array([r["o"] for r in rows]); c = np.array([r["c"] for r in rows])
    hours = ((t // H) % 24).astype(int)
    allowed = np.isin(hours, [(session_start + k) % 24 for k in range(3)])
    move = c / o - 1
    return np.where(allowed & (move <= -shock), 1, np.where(allowed & (move >= shock), -1, 0))


def simulate(rows, sig, hold, leverage, start, end, cost_mult=1.0):
    t = np.array([r["t"] for r in rows], dtype=np.int64)
    o = np.array([r["o"] for r in rows]); c = np.array([r["c"] for r in rows])
    i = max(0, int(np.searchsorted(t, start))); stop = int(np.searchsorted(t, end))
    equity = 1.0; peak = 1.0; mdd = 0.0; trades = 0; wins = 0
    while i + hold + 1 < stop:
        if sig[i] == 0 or t[i + 1] - t[i] != H:
            i += 1; continue
        entry_i = i + 1; exit_i = entry_i + hold - 1
        if t[exit_i] - t[entry_i] != (hold - 1) * H:
            i += 1; continue
        side = float(sig[i]); entry = o[entry_i] * (1 + side * .0002)
        exit_price = c[exit_i] * (1 - side * .0002)
        net = leverage * (side * (exit_price / entry - 1)
                          - (.0005 * 2 + .0000125 * hold) * cost_mult)
        equity *= max(.001, 1 + net); peak = max(peak, equity); mdd = min(mdd, equity / peak - 1)
        trades += 1; wins += net > 0
        # Preserve opportunity cooldown independently independently: selected entries are separated at least hold+1 hours apart.
        i = exit_i + 2
    return {"start_usd": 100.0, "end_usd": equity * 100, "return_pct": (equity - 1) * 100,
            "max_drawdown_pct": mdd * 100, "trades": trades,
            "win_rate_pct": wins / trades * 100 if trades else 0.0}


def main():
    OUT.mkdir(exist_ok=True)
    results = []
    for symbol in SYMBOLS:
        rows = core.read_candles(core.DATA_DIR / f"{symbol}USDT_1h.csv")
        ts = np.array([r["t"] for r in rows], dtype=np.int64)
        cuts = [int(ts[0] + (ts[-1] + H - ts[0]) * k / 3) for k in range(4)]
        cache = {(hour, shock): signal_for(rows, hour, shock) for hour, shock in itertools.product(SESSION_STARTS, SHOCKS)}
        grid = []
        for hour, shock, hold, lev in itertools.product(SESSION_STARTS, SHOCKS, HOLDS, LEVERAGES):
            sig = cache[(hour, shock)]
            seg = [simulate(rows, sig, hold, lev, cuts[k], cuts[k + 1]) for k in range(3)]
            grid.append({"utc_hours": [(hour + k) % 24 for k in range(3)], "shock": shock,
                         "hold_hours": hold, "leverage": lev, "segments": seg})
        nominees = []
        for origin in range(3):
            eligible = [x for x in grid if x["segments"][origin]["trades"] >= 8]
            best = max(eligible, key=lambda x: np.log(max(.001, x["segments"][origin]["end_usd"] / 100))
                       + x["segments"][origin]["max_drawdown_pct"] / 50)
            if best not in nominees:
                nominees.append(best)
        for rule in nominees:
            hour = rule["utc_hours"][0]; sig = cache[(hour, rule["shock"])]
            seg = [simulate(rows, sig, rule["hold_hours"], rule["leverage"], cuts[k], cuts[k + 1]) for k in range(3)]
            full = simulate(rows, sig, rule["hold_hours"], rule["leverage"], cuts[0], cuts[3])
            stress = simulate(rows, sig, rule["hold_hours"], rule["leverage"], cuts[0], cuts[3], 2.0)
            passed = bool(all(x["return_pct"] > 0 and x["trades"] >= 8 and x["max_drawdown_pct"] >= -50 for x in seg)
                          and full["return_pct"] >= 100_000 and full["max_drawdown_pct"] >= -50
                          and stress["return_pct"] > 0 and stress["max_drawdown_pct"] >= -60)
            results.append({"symbol": symbol, **{k: v for k, v in rule.items() if k != "segments"},
                            "segments": seg, "full": full, "double_cost": stress, "pass": passed})
        print("SYMBOL", symbol, "pass", sum(x["pass"] for x in results if x["symbol"] == symbol), flush=True)
    results.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    output = {"id": "SESSION-REVERSAL-STAGE89", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "live_changes": False,
              "method": "three-hour UTC session shock reversal; next-hour-open entry",
              "grid_per_symbol": len(SESSION_STARTS) * len(SHOCKS) * len(HOLDS) * len(LEVERAGES),
              "results": results,
              "limitations": ["Binance spot hourly proxy", "No BingX fill validation",
                              "Each third nominates rules; no untouched holdout", "No deployment"]}
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({"passing": sum(x["pass"] for x in results), "best": results[0] if results else None}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

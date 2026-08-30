from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

import replay_mdd30 as core


SYMBOLS = [p.name.replace("USDT_1h.csv", "") for p in sorted(core.DATA_DIR.glob("*USDT_1h.csv"))]
HOLDS = (1, 3, 6, 12, 24)
LEVERAGES = (0.5, 1.0, 2.0, 3.0, 5.0)
FEE_SIDE = 0.0005
SLIPPAGE_SIDE = 0.0002
FUNDING_8H = 0.0001
PRICE_CACHE: dict[int, tuple[np.ndarray, np.ndarray]] = {}


def prior_roll(x: np.ndarray, window: int, kind: str) -> np.ndarray:
    out = np.full(len(x), np.nan)
    for i in range(window, len(x)):
        z = x[i - window:i]
        out[i] = np.mean(z) if kind == "mean" else np.std(z) if kind == "std" else np.max(z) if kind == "max" else np.min(z)
    return out


def rsi_prior(close: np.ndarray, window: int) -> np.ndarray:
    change = np.zeros(len(close)); change[1:] = np.diff(close)
    out = np.full(len(close), np.nan)
    for i in range(window + 1, len(close)):
        z = change[i - window:i]
        gain = np.maximum(z, 0).mean(); loss = np.maximum(-z, 0).mean()
        out[i] = 100 if loss == 0 else 100 - 100 / (1 + gain / loss)
    return out


def signals(rows: list[dict]) -> list[tuple[str, dict, np.ndarray]]:
    o = np.array([r["o"] for r in rows]); h = np.array([r["h"] for r in rows])
    l = np.array([r["l"] for r in rows]); c = np.array([r["c"] for r in rows])
    v = np.array([r["v"] for r in rows]); ret = np.zeros(len(c)); ret[1:] = c[1:] / c[:-1] - 1
    hour = np.array([(int(r["t"]) // 3_600_000) % 24 for r in rows])
    result: list[tuple[str, dict, np.ndarray]] = []

    for w in (24, 72, 168):
        hi, lo = prior_roll(h, w, "max"), prior_roll(l, w, "min")
        for depth in (0.001, 0.003, 0.006):
            s = np.where((h > hi * (1 + depth)) & (c < hi), -1, np.where((l < lo * (1 - depth)) & (c > lo), 1, 0))
            result.append(("false_breakout_reentry", {"window": w, "depth": depth}, s))

    for w in (14, 24, 72):
        r = rsi_prior(c, w)
        for edge in (15, 20, 25, 30):
            result.append(("rsi_extreme_reversion", {"window": w, "edge": edge}, np.where(r <= edge, 1, np.where(r >= 100-edge, -1, 0))))

    for w in (24, 72, 168):
        mean, sd = prior_roll(c, w, "mean"), prior_roll(c, w, "std")
        z = np.divide(c - mean, sd, out=np.zeros(len(c)), where=sd > 0)
        for edge in (1.5, 2.0, 2.5, 3.0):
            result.append(("bollinger_extreme_reversion", {"window": w, "z": edge}, np.where(z <= -edge, 1, np.where(z >= edge, -1, 0))))

    absret = np.abs(ret)
    fast, slow = prior_roll(absret, 12, "mean"), prior_roll(absret, 168, "mean")
    volmean = prior_roll(v, 24, "mean")
    for ratio in (0.35, 0.5, 0.7):
        for expansion in (1.5, 2.0, 3.0):
            ready = (fast < slow * ratio) & (v > volmean * expansion)
            result.append(("squeeze_volume_expansion", {"compression": ratio, "volume": expansion}, np.where(ready, np.sign(ret), 0)))

    for session in ((0, 1, 2), (7, 8, 9), (13, 14, 15), (20, 21, 22)):
        active = np.isin(hour, session)
        for shock in (0.01, 0.02, 0.03, 0.05):
            result.append(("session_shock_reversion", {"utc_hours": session, "shock": shock}, np.where(active & (ret <= -shock), 1, np.where(active & (ret >= shock), -1, 0))))
    return result


def simulate(rows: list[dict], signal: np.ndarray, hold: int, leverage: float, start: int, end: int) -> dict:
    key = id(rows)
    if key not in PRICE_CACHE:
        PRICE_CACHE[key] = (np.array([r["o"] for r in rows]), np.array([r["c"] for r in rows]))
    o, c = PRICE_CACHE[key]
    possible = np.flatnonzero(signal[max(start, 169):max(start, end - hold - 1)]) + max(start, 169)
    chosen: list[int] = []
    next_allowed = -1
    for i in possible:
        if i >= next_allowed:
            chosen.append(int(i)); next_allowed = int(i) + hold + 1
    if not chosen:
        return {"multiple": 1.0, "return_pct": 0.0, "mdd_pct": 0.0, "trades": 0, "win_rate_pct": 0.0, "avg_trade_pct": 0.0}
    idx = np.array(chosen, dtype=int); direction = signal[idx]
    raw = direction * (c[idx + 1 + hold] / o[idx + 1] - 1) * leverage
    costs = (2 * (FEE_SIDE + SLIPPAGE_SIDE) + hold / 8 * FUNDING_8H) * leverage
    trade_returns = raw - costs
    factors = np.maximum(0.0, 1 + trade_returns); curve = np.cumprod(factors)
    peaks = np.maximum.accumulate(np.concatenate(([1.0], curve)))[1:]
    mdd = float(np.min(curve / peaks - 1)); equity = float(curve[-1])
    trades = len(chosen); wins = int(np.sum(trade_returns > 0))
    return {"multiple": equity, "return_pct": (equity - 1) * 100, "mdd_pct": mdd * 100,
            "trades": trades, "win_rate_pct": wins / trades * 100 if trades else 0,
            "avg_trade_pct": float(np.mean(trade_returns)) * 100}


def main() -> None:
    all_results = []
    for symbol in SYMBOLS:
        rows = core.read_candles(core.DATA_DIR / f"{symbol}USDT_1h.csv")
        PRICE_CACHE.clear()
        n = len(rows); cuts = (0, n // 3, 2 * n // 3, n)
        candidates = []
        for family, params, sig in signals(rows):
            for hold in HOLDS:
                for lev in LEVERAGES:
                    seg = [simulate(rows, sig, hold, lev, cuts[k], cuts[k+1]) for k in range(3)]
                    if min(x["trades"] for x in seg) < 15: continue
                    full = simulate(rows, sig, hold, lev, 0, n)
                    transferable = all(x["return_pct"] > 0 and x["mdd_pct"] >= -50 for x in seg)
                    score = min(np.log(max(x["multiple"], 1e-12)) for x in seg) + np.log(max(full["multiple"], 1e-12)) / 4
                    candidates.append({"symbol": symbol, "family": family, "params": params, "hold_hours": hold,
                                       "leverage": lev, "segments": seg, "full": full,
                                       "transferable": transferable, "score": float(score)})
        candidates.sort(key=lambda x: (x["transferable"], x["score"]), reverse=True)
        best = candidates[0] if candidates else None
        all_results.append({"symbol": symbol, "best": best, "tested": len(candidates)})
        print(json.dumps({"symbol": symbol, "tested": len(candidates), "best": best}, ensure_ascii=False), flush=True)

    transferable = [x["best"] for x in all_results if x["best"] and x["best"]["transferable"]]
    passing = [x for x in transferable if x["full"]["return_pct"] >= 1_000_000 and x["full"]["mdd_pct"] >= -50]
    output = {"generated_at": datetime.now(timezone.utc).isoformat(), "execution": "signal close; next bar open entry",
              "costs": {"fee_each_side": FEE_SIDE, "slippage_each_side": SLIPPAGE_SIDE, "funding_each_8h": FUNDING_8H},
              "symbols": SYMBOLS, "strategy_families": 5, "results": all_results,
              "transferable_count": len(transferable), "passing_1000000_count": len(passing), "passing": passing}
    path = core.RESULT_DIR / "novel_pattern_search_stage10.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"saved": str(path), "transferable": len(transferable), "passing": len(passing)}, ensure_ascii=False))


if __name__ == "__main__":
    main()

"""Futures/funding/adverse-path validation for A exposure scaling research."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import replay_mdd30 as a


ROOT = Path(__file__).resolve().parents[2]
DIR = ROOT / "research/results/a_exposure_scale_stage68"
SYMBOLS = ("BTC", "ETH", "XRP", "TRX", "SOL")
H = 3_600_000


def load():
    trees = a.load_trees()
    spot = {s: a.read_candles(a.DATA_DIR / f"{s}USDT_1h.csv") for s in SYMBOLS}
    maps = {s: a.targets(s, spot[s], trees[s], 0) for s in SYMBOLS}
    futures, funding = {}, {}
    for symbol in SYMBOLS:
        raw = json.loads((DIR / "data" / symbol / "hours.json").read_text())
        futures[symbol] = {int(x[0]): {"o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4])} for x in raw}
        fr = json.loads((DIR / "data" / symbol / "funding.json").read_text())
        funding[symbol] = {int(x["fundingTime"]) // H * H: float(x["fundingRate"]) for x in fr}
    return maps, futures, funding


def replay(maps, bars, funding, scale, fee, liquidation_move=.095):
    common = sorted(set.intersection(*(set(bars[s]) for s in SYMBOLS)))
    equity = peak = 1.0
    qty = {s: 0.0 for s in SYMBOLS}
    target = {s: 0.0 for s in SYMBOLS}
    entry = {s: None for s in SYMBOLS}
    liquidated_episode = {s: False for s in SYMBOLS}
    mdd = adverse_mdd = 0.0
    funding_paid = turnover = 0.0
    liquidation_events = []
    changes = 0
    for previous_t, current_t in zip(common, common[1:]):
        previous_equity = equity
        previous_close = {s: bars[s][previous_t]["c"] for s in SYMBOLS}
        for symbol in SYMBOLS:
            if current_t not in maps[symbol]:
                continue
            new_target = maps[symbol][current_t] * scale
            current_exposure = qty[symbol] * previous_close[symbol] / max(equity, 1e-15)
            delta = abs(new_target - current_exposure)
            equity *= max(0.0, 1.0 - delta * fee)
            turnover += delta
            # A publishes a fresh target at each daily decision boundary.  Live
            # reconciliation therefore resizes even when the signed tree leaf is
            # unchanged; treating it as a multi-day fixed quantity understates
            # turnover and misstates the effective entry/liquidation path.
            changes += 1
            target[symbol] = new_target
            qty[symbol] = new_target * equity / previous_close[symbol]
            entry[symbol] = previous_close[symbol] if new_target else None
            liquidated_episode[symbol] = False
        adverse_pnl = 0.0
        close_pnl = 0.0
        hour_funding = 0.0
        for symbol in SYMBOLS:
            q = qty[symbol]
            if not q:
                continue
            bar = bars[symbol][current_t]
            pc = previous_close[symbol]
            close_pnl += q * (bar["c"] - pc)
            adverse_pnl += q * ((bar["l"] - pc) if q > 0 else (bar["h"] - pc))
            rate = funding[symbol].get(current_t, 0.0)
            hour_funding += q * bar["c"] * rate
            if entry[symbol] and not liquidated_episode[symbol]:
                adverse = bar["l"] / entry[symbol] - 1 if q > 0 else 1 - bar["h"] / entry[symbol]
                if adverse <= -liquidation_move:
                    liquidation_events.append({"symbol": symbol, "time": current_t, "side": "long" if q > 0 else "short", "adverse_move_pct": adverse * 100})
                    liquidated_episode[symbol] = True
        adverse_equity = equity + adverse_pnl - hour_funding
        adverse_mdd = min(adverse_mdd, adverse_equity / peak - 1)
        equity = max(0.0, equity + close_pnl - hour_funding)
        funding_paid += hour_funding
        peak = max(peak, equity)
        mdd = min(mdd, equity / peak - 1)
        if previous_equity <= 0 or equity <= 0:
            break
    return {
        "start_usd": 100,
        "end_usd": equity * 100,
        "return_pct": (equity - 1) * 100,
        "close_mark_mdd_pct": mdd * 100,
        "hourly_adverse_bound_mdd_pct": adverse_mdd * 100,
        "allocation_changes": changes,
        "turnover_multiple": turnover,
        "net_funding_usd_per_100_initial": funding_paid * 100,
        "isolated_10x_liquidation_proxy_events": len(liquidation_events),
        "liquidation_examples": liquidation_events[:20],
    }


def main():
    maps, bars, funding = load()
    rows = []
    for scale in (1.0, 1.5, 2.0):
        for cost_name, fee in (("base_cost", .0004), ("double_cost", .0008)):
            rows.append({"scale": scale, "cost": cost_name, **replay(maps, bars, funding, scale, fee)})
    result = {
        "id": "A-EXPOSURE-SCALE-STAGE68",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "source": "frozen spot-tree signals replayed on complete Binance USD-M hourly futures and funding history",
        "range": ["2021-08-28", "2026-08-29"],
        "rows": rows,
        "limitations": [
            "9.5% isolated-liquidation move is a conservative proxy, not exact BingX tiered maintenance margin",
            "Hourly high/low adverse portfolio bound assumes all symbols hit their adverse extreme together",
            "No order-book fills or minute latency in this stage",
            "Historical signal trees are not an untouched holdout",
        ],
    }
    (DIR / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

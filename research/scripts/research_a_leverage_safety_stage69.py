"""Research-only A isolated-leverage safety grid on Binance USD-M hourly bars."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

import validate_a_exposure_scale_stage68 as s68


THRESHOLDS = {10: .095, 5: .19, 3: .315, 2: .475}


def main():
    maps, bars, _ = s68.load()
    rows = []
    per_symbol = {}
    worst = {symbol: 0.0 for symbol in s68.SYMBOLS}
    episodes = []
    common = set.intersection(*(set(bars[s]) for s in s68.SYMBOLS))
    for symbol in s68.SYMBOLS:
        times = sorted(t for t, target in maps[symbol].items() if target and t in common)
        for t in times:
            side = 1 if maps[symbol][t] > 0 else -1
            entry = bars[symbol][t]["o"]
            window = [bars[symbol][x] for x in range(t, t + 24 * s68.H, s68.H) if x in bars[symbol]]
            if not window:
                continue
            adverse = min((bar["l"] / entry - 1) if side > 0 else (1 - bar["h"] / entry) for bar in window)
            worst[symbol] = min(worst[symbol], adverse)
            episodes.append((symbol, t, side, adverse))
    for leverage, threshold in THRESHOLDS.items():
        hit = [x for x in episodes if x[3] <= -threshold]
        counts = Counter(x[0] for x in hit)
        rows.append({
            "exchange_leverage": leverage,
            "approx_liquidation_distance_pct": -threshold * 100,
            "required_margin_at_1_6x_gross_pct": 160 / leverage,
            "nonzero_daily_symbol_episodes": len(episodes),
            "liquidation_proxy_episodes": len(hit),
            "proxy_rate_pct": len(hit) / len(episodes) * 100,
            "by_symbol": dict(counts),
        })
    result = {
        "id": "A-LEVERAGE-SAFETY-STAGE69",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "range": ["2021-08-28", "2026-08-29"],
        "method": "Each nonzero daily A target is checked against the following 24 hourly futures high/lows; thresholds are conservative leverage proxies.",
        "rows": rows,
        "worst_24h_adverse_pct_by_symbol": {k: v * 100 for k, v in worst.items()},
        "limitations": [
            "Proxy thresholds are not BingX tier-specific liquidation prices.",
            "Overlapping daily episodes are diagnostic counts, not independent trades.",
            "Lowering exchange leverage does not change target notional/PnL, but requires more isolated margin.",
            "No live configuration change or deployment was made.",
        ],
    }
    out = s68.DIR.parent / "a_leverage_safety_stage69"
    out.mkdir(exist_ok=True)
    (out / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

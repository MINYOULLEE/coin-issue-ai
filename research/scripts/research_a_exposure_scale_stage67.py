from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import replay_mdd30 as base


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/results/a_exposure_scale_stage67/RESULTS.json"
SYMBOLS = ("BTC", "ETH", "XRP", "TRX", "SOL")
SCALES = (1.0, 1.25, 1.5, 1.75, 2.0)


def scaled_maps(maps, scale: float, gross_cap: float | None):
    result = {symbol: {} for symbol in SYMBOLS}
    times = sorted(set.intersection(*(set(maps[symbol]) for symbol in SYMBOLS)))
    for stamp in times:
        row = {symbol: maps[symbol][stamp] * scale for symbol in SYMBOLS}
        gross = sum(abs(value) for value in row.values())
        clip = min(1.0, gross_cap / gross) if gross_cap is not None and gross > 0 else 1.0
        for symbol, value in row.items():
            result[symbol][stamp] = value * clip
    return result


def compact(series, maps, fee):
    value = base.replay(series, maps, fee)
    return {
        "start_usd": 100.0,
        "end_usd": value["final_multiple"] * 100,
        "return_pct": value["return_pct"],
        "max_drawdown_pct": value["mdd_pct"],
        "allocation_changes": value["target_changes"],
    }


def compact_fixed(series, maps, fee):
    value = base.replay_daily(series, maps, fee)
    return {
        "start_usd": 100.0,
        "end_usd": value["final_multiple"] * 100,
        "return_pct": value["return_pct"],
        "max_drawdown_pct": value["mdd_pct"],
        "allocation_changes": value["target_changes"],
    }


def thirds(series, maps, fee, fixed=False):
    common = sorted(set.intersection(*(set(row["t"] for row in series[s]) for s in SYMBOLS)))
    cuts = (0, len(common) // 3, 2 * len(common) // 3, len(common))
    rows = []
    for index, (left, right) in enumerate(zip(cuts, cuts[1:]), 1):
        stamps = set(common[left:right])
        sliced_series = {s: [row for row in series[s] if row["t"] in stamps] for s in SYMBOLS}
        sliced_maps = {s: {t: v for t, v in maps[s].items() if t in stamps} for s in SYMBOLS}
        rows.append({"segment": index, **(compact_fixed(sliced_series, sliced_maps, fee) if fixed else compact(sliced_series, sliced_maps, fee))})
    return rows


def main():
    trees = base.load_trees()
    series = {s: base.read_candles(base.DATA_DIR / f"{s}USDT_1h.csv") for s in SYMBOLS}
    maps = {s: base.targets(s, series[s], trees[s], 0) for s in SYMBOLS}
    scenarios = []
    for scale in SCALES:
        for cap_mode, cap in (("current_cap_1.6x", 1.6), ("raised_cap_full_scale", None)):
            target = scaled_maps(maps, scale, cap)
            scenarios.append({
                "scale": scale,
                "cap_mode": cap_mode,
                "base_cost": compact(series, target, 0.0004),
                "double_cost": compact(series, target, 0.0008),
                "daily_fixed_notional_base_cost": compact_fixed(series, target, 0.0004),
                "daily_fixed_notional_double_cost": compact_fixed(series, target, 0.0008),
                "three_segments": thirds(series, target, 0.0004),
                "three_segments_daily_fixed_notional": thirds(series, target, 0.0004, fixed=True),
                "max_requested_gross_exposure": 1.6 * scale,
                "runtime_compatible_without_cap_change": scale == 1.0,
            })
    report = {
        "id": "A-EXPOSURE-SCALE-STAGE67",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "source": "current answer_mdd30 trees and cached Binance spot hourly OHLC",
        "range": ["2021-08-28", "2026-08-29"],
        "starting_capital_usd": 100,
        "decision_hour_utc": 0,
        "exchange_leverage": 10,
        "scenarios": scenarios,
        "limitations": [
            "Not deployed and does not change A live settings",
            "Binance spot hourly marks, not BingX fills, funding, maintenance margin, or tick liquidation",
            "Current-cap replay clips all symbols proportionately; production admission is sequential and may differ near the cap",
            "The same historical data trained the frozen answer trees, so this is not an independent holdout",
        ],
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

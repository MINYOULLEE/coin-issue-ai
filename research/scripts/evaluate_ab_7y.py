"""Replay the adopted A Stage75 and B Stage93 over the available 7-year inputs.

Research only. This script does not read or change live switches, credentials, or orders.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import replay_mdd30 as core


ROOT = Path(__file__).resolve().parents[2]
SPOT = ROOT / "research/data_7y"
FUTURES = ROOT / "research/data_7y_futures"
OUT = ROOT / "research/results/ab_7y_extension"
H = 3_600_000

# All imported research modules share this replay_mdd30 module object.
core.DATA_DIR = SPOT

import research_a_drawdown_guard_stage75 as a75
import validate_a_exposure_scale_stage68 as a68
import validate_b_algo_ada_combo_stage91 as b91


def iso(stamp):
    return datetime.fromtimestamp(stamp / 1000, timezone.utc).isoformat()


def compact(result):
    return {key: value for key, value in result.items() if key not in ("ledger", "stop_events")}


def evaluate_a():
    trees = core.load_trees()
    spot = {s: core.read_candles(SPOT / f"{s}USDT_1h.csv") for s in a68.SYMBOLS}
    maps = {s: core.targets(s, spot[s], trees[s], 0) for s in a68.SYMBOLS}
    bars, funding = {}, {}
    for symbol in a68.SYMBOLS:
        raw = json.loads((FUTURES / symbol / "hours.json").read_text(encoding="utf-8"))
        bars[symbol] = {int(x[0]): {"o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4])} for x in raw}
        rates = json.loads((FUTURES / symbol / "funding.json").read_text(encoding="utf-8"))
        funding[symbol] = {int(x["fundingTime"]) // H * H: float(x["fundingRate"]) for x in rates}
    common = sorted(set.intersection(*(set(bars[s]) for s in a68.SYMBOLS)))
    config = {"id": "guard35_075", "scale": 1.4, "dd_trigger": .35,
              "dd_reduced_scale": .75, "dd_recovery": .175}
    base = a75.run(maps, bars, funding, config)
    stress = a75.run(maps, bars, funding, config, stress=True)
    return {
        "plan": "A", "strategy_id": "answer_mdd30", "version": "mdd30_drawdown_guard_stage75_v1",
        "requested_range": ["2019-08-28", "2026-08-29"],
        "effective_range": [iso(common[0]), iso(common[-1] + H)],
        "late_start_reason": "SOL USD-M perpetual begins after the requested start; exact five-symbol A cannot run before all inputs exist.",
        "base_cost": compact(base), "double_cost_and_stop_slippage": compact(stress),
    }


def build_b_inputs():
    common = b91.s90.s86.s85.common
    series, core_entries, times = common.p.s.b.prepare()
    standard = json.loads((ROOT / "strategy/plan_b_combination_standard.json").read_text(encoding="utf-8"))
    core_busy = set()
    for positions in core_entries.values():
        for position in positions:
            core_busy.update(range(position["entry_ts"], position["exit_bar"] + H, H))
    ops = {}
    for ident in standard["reference"]["selector"]["patterns"]:
        symbol, pattern, _ = ident.split(":")
        if symbol == "ADA":
            continue
        rows = core.read_candles(SPOT / f"{symbol}USDT_1h.csv")
        for row in rows:
            row["symbol"] = symbol
        series[symbol] = {row["t"]: row for row in rows}
        if symbol == "ALGO":
            signal = dict(b91.s90.s86.s85.signal_grid(symbol, rows))[pattern]
        else:
            signal = dict(common.p.candidate_patterns(rows))[pattern]
        ops[symbol] = common.p.s.opportunities(
            rows, signal, 1, int(standard["symbols"][symbol]["leverage"]), core_busy
        )
    weights = {symbol: float(standard["symbols"][symbol]["target_margin_fraction"]) for symbol in ops}
    entries = b91.s90.s86.s85.stage40.entries_for(core_entries, ops, weights)

    ada_rows = core.read_candles(SPOT / "ADAUSDT_1h.csv")
    for row in ada_rows:
        row["symbol"] = "ADA"
    series["ADA"] = {row["t"]: row for row in ada_rows}
    ada_signal = b91.s90.s89.signal_for(ada_rows, 6, .03)
    ada_ops = b91.s90.s86.s85.common.p.s.opportunities(ada_rows, ada_signal, 7, 3, core_busy)
    for opportunity in ada_ops:
        entries.setdefault(opportunity["entry_ts"], []).append({**opportunity, "weight_scale": .25 / 1.15})

    features = {symbol: b91.s90.s86.s58.old.prev.features(list(rows.values())) for symbol, rows in series.items()}
    return series, core_entries, times, standard, ops, entries, features, ada_ops


def evaluate_b():
    series, _, times, standard, ops, entries, features, ada_ops = build_b_inputs()
    base, exits = b91.s90.s86.profit_lock_run(series, entries, times, features)
    stress, _ = b91.s90.s86.profit_lock_run(series, entries, times, features, cost_mult=2)
    return {
        "plan": "B", "strategy_id": "b_algo_ada_stage93", "version": "b_algo_ada_stage93_v1",
        "requested_range": ["2019-08-28", "2026-08-29"],
        "effective_range": [iso(times[0]), iso(times[-1] + H)],
        "late_start_reason": "The five-symbol B core requires ICP; exact Stage93 cannot run before ICP spot history exists.",
        "algo_opportunities": len(ops["ALGO"]), "ada_opportunities": len(ada_ops),
        "profit_lock_exits": exits, "base_cost": compact(base), "double_cost": compact(stress),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result = {
        "id": "AB-ADOPTED-SEVEN-YEAR-EXTENSION",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "live_changes": False,
        "plans": [evaluate_a(), evaluate_b()],
        "limitations": [
            "The requested calendar is seven years, but exact plan replays begin only when every required core market exists.",
            "A uses Binance USD-M hourly/funding; B retains its adopted Binance spot-hourly execution proxy.",
            "These strategy rules were selected using the later five-year sample, so the added earlier period is useful backward validation but not a future holdout.",
            "Historical results are not guaranteed future returns or exact BingX fills.",
        ],
    }
    (OUT / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

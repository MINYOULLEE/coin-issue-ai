"""Research only: futures-minute delay and collision verification for Stage91."""
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import validate_b_algo_ada_combo_stage91 as s91


H, M = 3_600_000, 60_000
OUT = s91.OUT.parent / "b_algo_ada_futures_stage92"
CACHE = OUT / "binance_futures_minutes"
DELAYS = (0, 1, 3, 5, 10)


def compact(x):
    return {k: v for k, v in x.items() if k != "ledger"}


def setup():
    series, core_entries, times, standard, ops = s91.s90.s86.s85.stage40.build()
    weights = {symbol: float(standard["symbols"][symbol]["target_margin_fraction"]) for symbol in ops}
    core_busy = set()
    for t, positions in core_entries.items():
        for position in positions:
            core_busy.update(range(t, position["exit_bar"] + H, H))
    algo_rows = [series["ALGO"][t] for t in sorted(series["ALGO"])]
    algo_sig = dict(s91.s90.s86.s85.signal_grid("ALGO", algo_rows))["capitulation_n3_move0.08_vol1.0_wick0.5"]
    ops["ALGO"] = s91.s90.s86.s85.common.p.s.opportunities(algo_rows, algo_sig, 1, 3, core_busy)
    entries = s91.s90.s86.s85.stage40.entries_for(core_entries, ops, weights)
    ada_rows = s91.s90.s86.s85.common.p.s.core.read_candles(s91.s90.s86.s85.common.p.s.core.DATA_DIR / "ADAUSDT_1h.csv")
    for row in ada_rows:
        row["symbol"] = "ADA"
    series["ADA"] = {r["t"]: r for r in ada_rows}
    ada_sig = s91.s90.s89.signal_for(ada_rows, 6, .03)
    ada_ops = s91.s90.s86.s85.common.p.s.opportunities(ada_rows, ada_sig, 7, 3, core_busy)
    for op in ada_ops:
        entries.setdefault(op["entry_ts"], []).append({**op, "weight_scale": .25 / 1.15})
    features = {symbol: s91.s90.s86.s58.old.prev.features(list(rows.values())) for symbol, rows in series.items()}
    return series, core_entries, times, entries, features, ops["ALGO"], ada_ops


def fetch(op):
    symbol = op["symbol"]; start = op["entry_ts"]; end = op["exit_bar"] + H
    path = CACHE / f"{symbol}_{start}.json"
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf8")); cached = True
    else:
        query = urllib.parse.urlencode({"symbol": symbol + "USDT", "interval": "1m",
                                        "startTime": start, "endTime": end - 1, "limit": 1000})
        req = urllib.request.Request("https://fapi.binance.com/fapi/v1/klines?" + query,
                                     headers={"User-Agent": "coin-issue-research/1.0"})
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = json.load(response)
        path.write_text(json.dumps(raw), encoding="utf8"); cached = False
    rows = {int(x[0]): {"o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4])} for x in raw}
    expected = list(range(start, end, M))
    if sorted(rows) != expected:
        raise RuntimeError(f"minute gap {symbol} {start}: {len(rows)}/{len(expected)}")
    return (symbol, start), rows, cached


def aggregate(rows, hour, first_minute=0):
    stamps = list(range(hour + first_minute * M, hour + H, M))
    return {"o": rows[stamps[0]]["o"], "h": max(rows[t]["h"] for t in stamps),
            "l": min(rows[t]["l"] for t in stamps), "c": rows[stamps[-1]]["c"]}


def main():
    OUT.mkdir(exist_ok=True); CACHE.mkdir(exist_ok=True)
    series, core_entries, times, entries, features, algo_ops, ada_ops = setup()
    candidates = algo_ops + ada_ops
    windows = {}; fetch_rows = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch, op): op for op in candidates}
        for future in as_completed(jobs):
            op = jobs[future]
            try:
                key, rows, cached = future.result(); windows[key] = rows
                fetch_rows.append({"symbol": key[0], "entry_ts": key[1], "cached": cached})
            except Exception as exc:
                fetch_rows.append({"symbol": op["symbol"], "entry_ts": op["entry_ts"], "error": str(exc)})
    errors = [x for x in fetch_rows if "error" in x]
    if errors:
        raise RuntimeError(f"minute fetch errors {len(errors)}: {errors[:3]}")

    scenarios = []
    for delay in DELAYS:
        trial_series = {symbol: dict(rows) for symbol, rows in series.items()}
        for op in candidates:
            key = (op["symbol"], op["entry_ts"]); minute = windows[key]
            for hour in range(op["entry_ts"], op["exit_bar"] + H, H):
                bar = aggregate(minute, hour, delay if hour == op["entry_ts"] else 0)
                bar.update({k: v for k, v in trial_series[op["symbol"]][hour].items() if k not in bar})
                trial_series[op["symbol"]][hour] = bar
        trial_features = {symbol: s91.s90.s86.s58.old.prev.features(list(rows.values())) for symbol, rows in trial_series.items()}
        full, _ = s91.s90.s86.profit_lock_run(trial_series, entries, times, trial_features)
        scenarios.append({"entry_delay_minutes": delay, **compact(full)})

    candidate_keys = {(x["symbol"], x["entry_ts"]) for x in candidates}
    existing = [x for rows in entries.values() for x in rows if (x["symbol"], x["entry_ts"]) not in candidate_keys]
    intervals = [(x["symbol"], x["entry_ts"], x["exit_bar"] + H) for x in candidates]
    collision = {
        "candidate_opportunities": len(candidates),
        "same_entry_with_existing": sum(any(x["entry_ts"] == start for x in existing) for _, start, _ in intervals),
        "holding_overlap_pairs_with_existing": sum(start < x["exit_bar"] + H and end > x["entry_ts"]
                                                   for _, start, end in intervals for x in existing),
        "candidate_internal_overlap_pairs": sum(a[1] < b[2] and a[2] > b[1]
                                                for i, a in enumerate(intervals) for b in intervals[i + 1:]),
    }
    output = {"id": "B-ALGO-ADA-FUTURES-STAGE92", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "live_changes": False, "orders_submitted": 0,
              "source": "Binance USD-M perpetual public 1-minute klines",
              "windows": len(windows), "fetch_errors": errors, "scenarios": scenarios, "collision": collision,
              "pass_under_live_ttl": all(x["return_pct"] > 1_000_000 and x["hourly_mark_mdd_pct"] >= -70
                                         and x["hourly_adverse_bound_pct"] >= -70
                                         and not x["liquidation_proxy_count"] for x in scenarios if x["entry_delay_minutes"] < 5),
              "limitations": ["Binance futures proxy, not BingX fills", "Historical sample used in discovery",
                              "No untouched forward holdout", "No live orders or deployment"]}
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

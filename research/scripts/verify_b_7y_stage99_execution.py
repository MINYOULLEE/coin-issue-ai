"""Futures-minute execution stress for the Stage98 3.5x candidate."""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import evaluate_ab_7y as ab
import repair_b_7y_stage97 as s97


HOUR, MINUTE = 3_600_000, 60_000
OUT = ab.OUT / "B_STAGE99_EXECUTION_VALIDATION.json"
CACHE = ab.ROOT / "research/results/b_algo_ada_futures_stage92/binance_futures_minutes"


def compact(result):
    return {key: value for key, value in result.items() if key != "ledger"}


def fetch(op):
    symbol, start, end = op["symbol"], op["entry_ts"], op["exit_bar"] + HOUR
    path = CACHE / f"{symbol}_{start}.json"
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8")); cached = True
    else:
        query = urllib.parse.urlencode({"symbol": symbol + "USDT", "interval": "1m",
                                        "startTime": start, "endTime": end - 1, "limit": 1000})
        request = urllib.request.Request("https://fapi.binance.com/fapi/v1/klines?" + query,
                                         headers={"User-Agent": "coin-issue-research/1.0"})
        with urllib.request.urlopen(request, timeout=30) as response:
            raw = json.load(response)
        path.write_text(json.dumps(raw), encoding="utf-8"); cached = False
    rows = {int(x[0]): {"o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4])} for x in raw}
    expected = list(range(start, end, MINUTE))
    if not rows:
        return (symbol, start), None, cached
    if sorted(rows) != expected:
        raise RuntimeError(f"minute gap {symbol} {start}: {len(rows)}/{len(expected)}")
    return (symbol, start), rows, cached


def aggregate(rows, hour, first_minute=0):
    stamps = list(range(hour + first_minute*MINUTE, hour + HOUR, MINUTE))
    return {"o": rows[stamps[0]]["o"], "h": max(rows[t]["h"] for t in stamps),
            "l": min(rows[t]["l"] for t in stamps), "c": rows[stamps[-1]]["c"]}


def learned_exits(series, entries, features):
    exits = {}
    for symbol, (quantile, keep, conditional) in ab.b91.s90.s86.CHOICES.items():
        learned, _ = ab.b91.s90.s86.s61.learned_profit_locks(
            series, entries, features, symbol.lower(), quantile, keep, conditional)
        exits.update(learned)
    return exits


def main():
    CACHE.mkdir(parents=True, exist_ok=True)
    series, _, times, _, ops, entries, _, ada_ops = ab.build_b_inputs()
    candidates = ops["ALGO"] + ada_ops
    windows, fetched, errors, unavailable = {}, [], [], []
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch, op): op for op in candidates}
        for future in as_completed(jobs):
            op = jobs[future]
            try:
                key, rows, cached = future.result()
                if rows is None:
                    unavailable.append({"symbol": key[0], "entry_ts": key[1],
                                        "reason": "USD-M perpetual minute window unavailable"})
                else:
                    windows[key] = rows
                fetched.append({"symbol": key[0], "entry_ts": key[1], "cached": cached})
            except Exception as exc:
                errors.append({"symbol": op["symbol"], "entry_ts": op["entry_ts"], "error": str(exc)})
    if errors:
        raise RuntimeError(f"minute fetch errors {len(errors)}: {errors[:3]}")
    unavailable_keys = {(x["symbol"], x["entry_ts"]) for x in unavailable}
    candidates = [x for x in candidates if (x["symbol"], x["entry_ts"]) not in unavailable_keys]
    entries = {stamp: [x for x in rows if (x["symbol"], x["entry_ts"]) not in unavailable_keys]
               for stamp, rows in entries.items()}

    scenarios = []
    for delay in (0, 1, 3, 5):
        trial = {symbol: dict(rows) for symbol, rows in series.items()}
        for op in candidates:
            minute = windows[(op["symbol"], op["entry_ts"])]
            for hour in range(op["entry_ts"], op["exit_bar"] + HOUR, HOUR):
                bar = aggregate(minute, hour, delay if hour == op["entry_ts"] else 0)
                bar.update({key: value for key, value in trial[op["symbol"]][hour].items() if key not in bar})
                trial[op["symbol"]][hour] = bar
        features = {symbol: ab.b91.s90.s86.s58.old.prev.features(list(rows.values())) for symbol, rows in trial.items()}
        exits = learned_exits(trial, entries, features)
        fn = s97.runner(exits, 3.5)
        base = fn(trial, entries, times, 1.15)
        stress = fn(trial, entries, times, 1.15, cost_mult=2)
        scenarios.append({"entry_delay_minutes": delay, "base": compact(base), "double_cost": compact(stress)})

    result = {
        "id": "B-STAGE99-SEVEN-YEAR-FUTURES-MINUTE-EXECUTION-VALIDATION",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True, "live_changes": False, "orders_submitted": 0,
        "candidate": {"max_entry_gross_equity_ratio": 3.5, "drawdown_trigger_pct": 30,
                      "new_entry_cooldown_hours": 240},
        "source": "Binance USD-M perpetual public 1-minute klines for ALGO/ADA candidate windows",
        "windows": len(windows), "downloaded": sum(not x["cached"] for x in fetched),
        "unavailable_futures_opportunities": unavailable,
        "fetch_errors": errors, "scenarios": scenarios,
        "pass_live_ttl": all(
            x["base"]["return_pct"] >= 1_000_000
            and x["base"]["hourly_adverse_bound_pct"] >= -70
            and x["double_cost"]["hourly_adverse_bound_pct"] >= -70
            and x["base"]["liquidation_proxy_count"] == 0
            and x["double_cost"]["liquidation_proxy_count"] == 0
            for x in scenarios if x["entry_delay_minutes"] < 5),
        "limitations": [
            "Minute substitution covers ALGO/ADA candidate windows; other Stage93 families remain hourly.",
            "Binance USD-M is an execution proxy, not actual BingX fills or order-book depth.",
            "Five-minute delay is a boundary stress and does not relax the production TTL below five minutes.",
            "No live state, orders, switches, or adopted standards changed.",
        ],
    }
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()

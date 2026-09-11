"""Minute-delay execution audit for the frozen Stage132 A rally-guard candidate."""
from __future__ import annotations

import hashlib
import json
import statistics
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import research_a_intraday_rally_guard_stage127 as s127
import research_ab_reinforcement_stage113 as s113
import research_a_sol_short_refinement_stage115 as s115

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "research/results/ab_7y_extension/A_STAGE132_RALLY_GUARD_MDD_REFINEMENT.json"
OUT = ROOT / "research/results/a_rally_guard_minutes_stage133"
CACHE = OUT / "binance_futures_minutes"
RESULT = OUT / "RESULTS.json"
HOUR = 3_600_000
MINUTE = 60_000
DELAYS = (0, 1, 3, 5, 10)


def get(url):
    request = urllib.request.Request(url, headers={"User-Agent": "coin-issue-research/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch(event):
    symbol, stamp = event["symbol"], event["time"]
    path = CACHE / f"{symbol}_{stamp}.json"
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        query = urllib.parse.urlencode({
            "symbol": symbol + "USDT",
            "interval": "1m",
            "startTime": stamp,
            "endTime": stamp + 11 * MINUTE - 1,
            "limit": 11,
        })
        raw = get("https://fapi.binance.com/fapi/v1/klines?" + query)
        path.write_text(json.dumps(raw), encoding="utf-8")
    rows = {int(row[0]): float(row[1]) for row in raw}
    expected = [stamp + delay * MINUTE for delay in DELAYS]
    if any(point not in rows for point in expected):
        raise ValueError(f"minute gap {symbol} {stamp}: {len(rows)}/11")
    return (symbol, stamp), rows


def percentile(values, q):
    ordered = sorted(values)
    if not ordered:
        return None
    position = (len(ordered) - 1) * q
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    weight = position - lower
    return ordered[lower] * (1 - weight) + ordered[upper] * weight


def main():
    OUT.mkdir(exist_ok=True)
    CACHE.mkdir(exist_ok=True)
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    winner = source["ranked"][0]
    cfg = winner["config"]
    maps, bars, funding = s113.a_inputs()
    start = min(set.intersection(*(set(bars[symbol]) for symbol in s127.SYMBOLS)))
    maps = s115.filtered(maps, bars, 0.035, 0.12, 3, 0)
    replay = s127.replay(maps, bars, funding, cfg, start, s127.END)
    events = list({(event["symbol"], event["time"]): event for event in replay["overlay_events"]}.values())

    windows, errors = {}, []
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch, event): event for event in events}
        for index, future in enumerate(as_completed(jobs), 1):
            event = jobs[future]
            try:
                key, rows = future.result()
                windows[key] = rows
            except Exception as exc:
                errors.append({"symbol": event["symbol"], "time": event["time"], "error": str(exc)})
            if index % 50 == 0:
                print("fetched", index, flush=True)

    details = []
    for event in events:
        key = (event["symbol"], event["time"])
        if key not in windows:
            continue
        rows = windows[key]
        immediate = rows[event["time"]]
        for delay in DELAYS:
            price = rows[event["time"] + delay * MINUTE]
            # All overlay actions close shorts, therefore a positive price move is adverse.
            drift = (price / immediate - 1) * 100
            details.append({**event, "delay_min": delay, "minute_open": price, "adverse_drift_pct": drift})

    summaries = []
    for delay in DELAYS:
        values = [row["adverse_drift_pct"] for row in details if row["delay_min"] == delay]
        summaries.append({
            "delay_min": delay,
            "events": len(values),
            "mean_adverse_drift_pct": statistics.mean(values) if values else None,
            "median_adverse_drift_pct": statistics.median(values) if values else None,
            "p95_adverse_drift_pct": percentile(values, 0.95),
            "p99_adverse_drift_pct": percentile(values, 0.99),
            "worst_adverse_drift_pct": max(values) if values else None,
            "favorable_or_flat_count": sum(value <= 0 for value in values),
            "above_0_3pct_count": sum(value > 0.3 for value in values),
            "above_0_5pct_count": sum(value > 0.5 for value in values),
        })

    by_hour = {}
    for event in events:
        by_hour.setdefault(event["time"], []).append(event)
    result = {
        "id": "A-STAGE133-RALLY-GUARD-MINUTE-EXECUTION",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "research_only": True,
        "orders_submitted": 0,
        "candidate": cfg,
        "requested_events": len(events),
        "complete_events": len(windows),
        "unique_trigger_hours": len(by_hour),
        "simultaneous_symbol_max": max(map(len, by_hour.values()), default=0),
        "errors": errors,
        "summaries": summaries,
        "details": details,
        "hashes": {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in CACHE.glob("*.json")},
        "limitations": [
            "Binance USD-M one-minute opens approximate market execution; they are not BingX order-book fills.",
            "The selected trigger windows are in-sample historical events, not future/live validation.",
            "Network delay and partial-fill behavior are represented only by delayed minute opens and separate slippage stress.",
        ],
    }
    RESULT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({key: value for key, value in result.items() if key not in ("details", "hashes")}, ensure_ascii=False))


if __name__ == "__main__":
    main()

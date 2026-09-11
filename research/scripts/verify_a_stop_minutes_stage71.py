"""Minute-level trigger/fill audit for A Stage70 1.5x/4x/15% candidate."""
from __future__ import annotations

import hashlib
import json
import statistics
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "research/results/a_scale_stop_stage70/RESULTS.json"
OUT = ROOT / "research/results/a_stop_minutes_stage71"
CACHE = OUT / "binance_futures_minutes"
M = 60_000
H = 3_600_000


def get(url):
    request = urllib.request.Request(url, headers={"User-Agent": "coin-issue-research/1.0"})
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.load(response)


def fetch(event):
    symbol, t = event["symbol"], event["time"]
    path = CACHE / f"{symbol}_{t}.json"
    if path.exists():
        raw = json.loads(path.read_text(encoding="utf-8"))
    else:
        query = urllib.parse.urlencode({"symbol": symbol + "USDT", "interval": "1m", "startTime": t,
                                       "endTime": t + H - 1, "limit": 60})
        raw = get("https://fapi.binance.com/fapi/v1/klines?" + query)
        path.write_text(json.dumps(raw), encoding="utf-8")
    rows = {int(x[0]): {"o": float(x[1]), "h": float(x[2]), "l": float(x[3]), "c": float(x[4])} for x in raw}
    expected = list(range(t, t + H, M))
    if sorted(rows) != expected:
        raise ValueError(f"minute gap {symbol} {t}: {len(rows)}/60")
    return (symbol, t), rows


def audit(event, rows, delay):
    side = 1 if event["side"] == "long" else -1
    threshold = event["threshold"]
    liquidation = event["entry"] * (1 - side * .2375)
    trigger = None
    same_minute_liquidation = False
    for stamp in sorted(rows):
        bar = rows[stamp]
        touched = bar["l"] <= threshold if side > 0 else bar["h"] >= threshold
        if touched:
            trigger = stamp
            same_minute_liquidation = bar["l"] <= liquidation if side > 0 else bar["h"] >= liquidation
            break
    if trigger is None:
        return {"confirmed": False, "delay_min": delay}
    fill_stamp = min(trigger + delay * M, max(rows))
    path = [rows[x] for x in sorted(rows) if trigger <= x <= fill_stamp]
    liquidation_before_fill = any(x["l"] <= liquidation for x in path) if side > 0 else any(x["h"] >= liquidation for x in path)
    worst_path_return = min(side * ((x["l"] if side > 0 else x["h"]) / event["entry"] - 1) * 100 for x in path)
    raw_fill = threshold if delay == 0 else rows[fill_stamp]["o"]
    fill = raw_fill * (1 - side * .003)  # adverse 0.3% market-fill stress
    loss_pct = side * (fill / event["entry"] - 1) * 100
    return {"confirmed": True, "delay_min": delay, "trigger_minute": trigger,
            "fill_minute": fill_stamp, "stressed_fill": fill, "position_return_pct": loss_pct,
            "same_minute_liquidation_ambiguity": same_minute_liquidation,
            "liquidation_before_fill_proxy": liquidation_before_fill,
            "worst_path_position_return_pct": worst_path_return}


def main():
    OUT.mkdir(exist_ok=True)
    CACHE.mkdir(exist_ok=True)
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    candidate = next(x for x in source["rows"] if x["scale"] == 1.4 and x["stop_pct"] == 15)
    events = candidate["base"]["stop_events"]
    windows, errors = {}, []
    with ThreadPoolExecutor(max_workers=4) as pool:
        jobs = {pool.submit(fetch, x): x for x in events}
        for future in as_completed(jobs):
            event = jobs[future]
            try:
                key, rows = future.result()
                windows[key] = rows
            except Exception as exc:
                errors.append({"symbol": event["symbol"], "time": event["time"], "error": str(exc)})
    details = []
    for event in events:
        key = (event["symbol"], event["time"])
        if key not in windows:
            continue
        for delay in (0, 1, 3, 5, 10):
            details.append({"symbol": event["symbol"], "time": event["time"], "side": event["side"],
                            **audit(event, windows[key], delay)})
    summaries = []
    for delay in (0, 1, 3, 5, 10):
        xs = [x for x in details if x["delay_min"] == delay and x["confirmed"]]
        losses = [x["position_return_pct"] for x in xs]
        summaries.append({"delay_min": delay, "confirmed": len(xs),
                          "mean_position_return_pct": statistics.mean(losses) if losses else None,
                          "median_position_return_pct": statistics.median(losses) if losses else None,
                          "worst_position_return_pct": min(losses) if losses else None,
                          "better_than_immediate_count": sum(x > -15.3 for x in losses),
                          "worse_than_immediate_count": sum(x < -15.3 for x in losses),
                          "same_minute_liquidation_ambiguities": sum(x["same_minute_liquidation_ambiguity"] for x in xs),
                          "liquidation_before_fill_proxy_count": sum(x["liquidation_before_fill_proxy"] for x in xs),
                          "liquidation_proxy_counts_by_leverage": {
                              str(leverage): sum(x["worst_path_position_return_pct"] <= -(95 / leverage) for x in xs)
                              for leverage in (3, 3.5, 4, 5)
                          }})
    result = {"id": "A-STOP-MINUTES-STAGE71", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "orders_submitted": 0, "candidate": "A 1.4x notional / 3x isolated / 15% emergency stop",
              "requested_windows": len(events), "complete_windows": len(windows), "errors": errors,
              "summaries": summaries, "details": details,
              "hashes": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in CACHE.glob("*.json")},
              "limitations": ["Binance USD-M public minutes, not BingX order-book fills or mark-price triggers.",
                              "Only historically triggered stop hours were selected; not an independent holdout.",
                              "Same-minute stop/liquidation ordering is unknowable from OHLC and is reported as ambiguous."]}
    (OUT / "RESULTS.json").write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in result.items() if k not in ("details", "hashes")}, ensure_ascii=False))


if __name__ == "__main__":
    main()

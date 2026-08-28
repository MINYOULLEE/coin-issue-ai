from __future__ import annotations

import argparse
import csv
import json
import math
import re
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")


ROOT = Path(__file__).resolve().parents[2]
TREE_FILE = ROOT / "supabase/functions/coin-collector/answer_trees.ts"
DATA_DIR = ROOT / "research/data"
RESULT_DIR = ROOT / "research/results"
FEATURES = [
    "return_1h", "return_3h", "return_6h", "return_12h", "return_24h",
    "return_72h", "return_168h", "return_336h", "return_720h",
    "ema_gap_12_72", "ema_gap_24_168", "ema_gap_72_336", "ema_gap_168_720",
    "channel_24", "vol_24", "channel_72", "vol_72", "channel_168",
    "vol_168", "channel_336", "vol_336", "channel_720", "vol_720",
    "rsi_14", "rsi_72", "rsi_168", "atr_24", "atr_72", "atr_168",
    "body", "upper_wick", "lower_wick", "volume_rank_30d",
    "dollar_volume_rank_30d", "volume_change_24h",
]
CONFIG = {
    "BTC": (.125, .55, .75, .5, 1.5, 2.0),
    "ETH": (.275, .45, .70, 0.0, 1.0, 1.5),
    "XRP": (.10, .45, .60, 0.0, .5, 1.5),
    "TRX": (.40, .45, .60, 0.0, 1.0, 1.0),
    "SOL": (.30, .45, .60, 0.0, 1.0, 1.0),
}


def load_trees() -> dict[str, dict]:
    text = TREE_FILE.read_text(encoding="utf-8")
    trees = {}
    for symbol in CONFIG:
        match = re.search(rf"const {symbol} = (\{{.*?\}}) as const;", text)
        if not match:
            raise RuntimeError(f"missing tree: {symbol}")
        trees[symbol] = json.loads(match.group(1))
    return trees


def request_klines(symbol: str, start_ms: int, end_ms: int) -> list[list]:
    query = urllib.parse.urlencode({
        "symbol": f"{symbol}USDT", "interval": "1h", "limit": 1000,
        "startTime": start_ms, "endTime": end_ms,
    })
    req = urllib.request.Request(
        "https://api.binance.com/api/v3/klines?" + query,
        headers={"User-Agent": "coin-issue-ai-research/1.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def download(symbol: str, start_ms: int, end_ms: int) -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    path = DATA_DIR / f"{symbol}USDT_1h.csv"
    existing: dict[int, list[str]] = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                existing[int(row["open_time"])] = [row[k] for k in (
                    "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "quote_volume",
                )]
    cursor = max(existing, default=start_ms - 3_600_000) + 3_600_000
    cursor = max(cursor, start_ms)
    while cursor <= end_ms:
        rows = request_klines(symbol, cursor, end_ms)
        if not rows:
            break
        for row in rows:
            existing[int(row[0])] = [str(row[i]) for i in range(8)]
        next_cursor = int(rows[-1][0]) + 3_600_000
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        time.sleep(.05)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume"])
        writer.writerows(existing[key] for key in sorted(existing) if start_ms <= key <= end_ms)
    return path


def read_candles(path: Path) -> list[dict]:
    with path.open(newline="", encoding="utf-8") as handle:
        return [{
            "t": int(r["open_time"]), "o": float(r["open"]), "h": float(r["high"]),
            "l": float(r["low"]), "c": float(r["close"]), "v": float(r["volume"]),
            "q": float(r["quote_volume"]),
        } for r in csv.DictReader(handle)]


def ema(values: list[float], period: int) -> float:
    alpha = 2 / (period + 1)
    value = values[0]
    for item in values[1:]:
        value = alpha * item + (1 - alpha) * value
    return value


def sample_std(values: list[float]) -> float:
    if len(values) < 2:
        return 0.0
    mean = sum(values) / len(values)
    return math.sqrt(sum((x - mean) ** 2 for x in values) / (len(values) - 1))


def percentile_rank(values: list[float], current: float) -> float:
    below = sum(x < current for x in values)
    equal = sum(x == current for x in values)
    return (below + (equal + 1) / 2) / len(values)


def feature_vector(rows: list[dict]) -> list[float]:
    z = rows[-1000:]
    o = [x["o"] for x in z]; h = [x["h"] for x in z]
    l = [x["l"] for x in z]; c = [x["c"] for x in z]
    v = [x["v"] for x in z]; q = [x["q"] for x in z]
    last = len(c) - 1
    returns = [c[i] / c[i - 1] - 1 for i in range(1, len(c))]
    values: dict[str, float] = {}
    for n in (1, 3, 6, 12, 24, 72, 168, 336, 720):
        values[f"return_{n}h"] = c[last] / c[last - n] - 1
    for fast, slow in ((12, 72), (24, 168), (72, 336), (168, 720)):
        values[f"ema_gap_{fast}_{slow}"] = ema(c, fast) / ema(c, slow) - 1
    for n in (24, 72, 168, 336, 720):
        hi = max(h[last - n:last]); lo = min(l[last - n:last])
        values[f"channel_{n}"] = (c[last] - lo) / (hi - lo or 1)
        values[f"vol_{n}"] = sample_std(returns[-n:]) * math.sqrt(365.25 * 24)
    for n in (14, 72, 168):
        rr = returns[-n:]
        gain = sum(max(x, 0) for x in rr) / n
        loss = sum(max(-x, 0) for x in rr) / n
        values[f"rsi_{n}"] = 100 - 100 / (1 + gain / loss) if loss else 100
    tr = [max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])) for i in range(1, len(c))]
    for n in (24, 72, 168):
        values[f"atr_{n}"] = sum(tr[-n:]) / n / c[last]
    values["body"] = (c[last] - o[last]) / o[last]
    values["upper_wick"] = (h[last] - max(o[last], c[last])) / c[last]
    values["lower_wick"] = (min(o[last], c[last]) - l[last]) / c[last]
    values["volume_rank_30d"] = percentile_rank(v[-720:], v[last])
    values["dollar_volume_rank_30d"] = percentile_rank(q[-720:], q[last])
    values["volume_change_24h"] = v[last] / v[last - 24] - 1
    return [values[name] for name in FEATURES]


def evaluate(tree: dict, vector: list[float]) -> tuple[int, float, int]:
    node = 0
    while tree["left"][node] != -1:
        node = tree["left"][node] if vector[tree["feature"][node]] <= tree["threshold"][node] else tree["right"][node]
    probabilities = tree["probability"][node]
    index = max(range(len(probabilities)), key=probabilities.__getitem__)
    return int(tree["classes"][index]), float(probabilities[index]), node


def targets(symbol: str, candles: list[dict], tree: dict, decision_hour: int) -> dict[int, float]:
    weight, low, high, low_x, mid_x, high_x = CONFIG[symbol]
    result = {}
    for i in range(720, len(candles)):
        # Decision is made only after this completed UTC hourly candle.
        if datetime.fromtimestamp(candles[i]["t"] / 1000, timezone.utc).hour != decision_hour:
            continue
        direction, confidence, _ = evaluate(tree, feature_vector(candles[:i + 1]))
        raw = low_x if confidence < low else mid_x if confidence < high else high_x
        result[candles[i]["t"] + 3_600_000] = direction * raw * weight
    return result


def replay(series: dict[str, list[dict]], target_maps: dict[str, dict[int, float]], fee: float) -> dict:
    common = sorted(set.intersection(*(set(x["t"] for x in rows) for rows in series.values())))
    price = {s: {x["t"]: x["c"] for x in rows} for s, rows in series.items()}
    positions = {s: 0.0 for s in series}; equity = 1.0; peak = 1.0; mdd = 0.0
    changes = 0; started = False
    for previous_t, current_t in zip(common, common[1:]):
        for symbol in series:
            if current_t in target_maps[symbol]:
                new = target_maps[symbol][current_t]
                equity *= max(0.0, 1 - abs(new - positions[symbol]) * fee)
                changes += new != positions[symbol]
                positions[symbol] = new
                started = True
        if not started:
            continue
        portfolio_return = sum(positions[s] * (price[s][current_t] / price[s][previous_t] - 1) for s in series)
        equity *= max(0.0, 1 + portfolio_return)
        peak = max(peak, equity)
        mdd = min(mdd, equity / peak - 1)
    return {"final_multiple": equity, "return_pct": (equity - 1) * 100, "mdd_pct": mdd * 100, "target_changes": changes}


def replay_daily(series: dict[str, list[dict]], target_maps: dict[str, dict[int, float]], fee: float) -> dict:
    """Replay fixed notionals between daily decisions (no implicit hourly rebalance)."""
    price = {s: {x["t"]: x["c"] for x in rows} for s, rows in series.items()}
    decision_times = sorted(set.intersection(*(set(m) for m in target_maps.values())))
    equity = 1.0; peak = 1.0; mdd = 0.0; positions = {s: 0.0 for s in series}; changes = 0
    for current_t, next_t in zip(decision_times, decision_times[1:]):
        for symbol in series:
            new = target_maps[symbol][current_t]
            equity *= max(0.0, 1 - abs(new - positions[symbol]) * fee)
            changes += new != positions[symbol]
            positions[symbol] = new
        start_price_t = current_t - 3_600_000
        end_price_t = next_t - 3_600_000
        portfolio_return = sum(
            positions[s] * (price[s][end_price_t] / price[s][start_price_t] - 1)
            for s in series
        )
        equity *= max(0.0, 1 + portfolio_return)
        peak = max(peak, equity)
        mdd = min(mdd, equity / peak - 1)
    return {"final_multiple": equity, "return_pct": (equity - 1) * 100, "mdd_pct": mdd * 100, "target_changes": changes}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--symbols", nargs="+", default=["BTC", "ETH", "XRP", "TRX", "SOL", "BNB"])
    parser.add_argument("--start", default="2021-08-28")
    parser.add_argument("--end", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--download-only", action="store_true")
    args = parser.parse_args()
    start_ms = int(datetime.fromisoformat(args.start).replace(tzinfo=timezone.utc).timestamp() * 1000)
    end_ms = int(datetime.fromisoformat(args.end).replace(tzinfo=timezone.utc).timestamp() * 1000) + 86_399_999
    paths = {s: download(s, start_ms, end_ms) for s in args.symbols}
    if args.download_only:
        print(json.dumps({"downloaded": args.symbols, "paths": {s: str(p) for s, p in paths.items()}}, ensure_ascii=False, indent=2))
        return
    trees = load_trees()
    baseline_symbols = [s for s in args.symbols if s in trees]
    series = {s: read_candles(paths[s]) for s in baseline_symbols}
    reports = []
    for hour in (0, 23):
        maps = {s: targets(s, series[s], trees[s], hour) for s in baseline_symbols}
        for fee in (0.0, .0004, .0005, .0006, .0010):
            reports.append({"method": "hourly_mark", "decision_hour_utc": hour, "fee_per_turnover": fee, **replay(series, maps, fee)})
            reports.append({"method": "daily_fixed_notional", "decision_hour_utc": hour, "fee_per_turnover": fee, **replay_daily(series, maps, fee)})
    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(), "range": [args.start, args.end],
        "symbols_downloaded": args.symbols, "baseline_symbols": baseline_symbols,
        "candle_counts": {s: sum(1 for _ in read_candles(p)) for s, p in paths.items()},
        "calibration_grid": reports,
    }
    RESULT_DIR.mkdir(parents=True, exist_ok=True)
    output = RESULT_DIR / "mdd30_baseline_replay.json"
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()

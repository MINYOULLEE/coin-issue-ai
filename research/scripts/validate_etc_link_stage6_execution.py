from __future__ import annotations

import csv
import json
import math
import time
import urllib.parse
import urllib.request
from pathlib import Path

import numpy as np

import replay_mdd30 as core
from search_intraday_patterns import indicators, pattern_signal

SYMBOLS = ("ETC", "LINK")
FIVE_MIN = 300_000
START = 1630108800000
END = 1787903999999


def download_5m(symbol: str) -> Path:
    path = core.DATA_DIR / f"{symbol}USDT_5m.csv"
    existing: dict[int, list[str]] = {}
    if path.exists():
        with path.open(newline="", encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                existing[int(row["open_time"])] = [row[k] for k in (
                    "open_time", "open", "high", "low", "close", "volume",
                    "close_time", "quote_volume",
                )]
    cursor = max(existing, default=START - FIVE_MIN) + FIVE_MIN
    while cursor <= END:
        query = urllib.parse.urlencode({
            "symbol": f"{symbol}USDT", "interval": "5m", "limit": 1000,
            "startTime": cursor, "endTime": END,
        })
        req = urllib.request.Request(
            "https://api.binance.com/api/v3/klines?" + query,
            headers={"User-Agent": "coin-issue-ai-execution-validation/1.0"},
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            rows = json.load(response)
        if not rows:
            break
        for row in rows:
            existing[int(row[0])] = [str(row[i]) for i in range(8)]
        nxt = int(rows[-1][0]) + FIVE_MIN
        if nxt <= cursor:
            break
        cursor = nxt
        if len(existing) % 50_000 < 1000:
            print(json.dumps({"download": symbol, "rows": len(existing)}, ensure_ascii=False), flush=True)
        time.sleep(.04)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["open_time", "open", "high", "low", "close", "volume", "close_time", "quote_volume"])
        writer.writerows(existing[k] for k in sorted(existing) if START <= k <= END)
    return path


def prices_5m(path: Path) -> tuple[dict[int, float], dict[int, float]]:
    opens, closes = {}, {}
    with path.open(newline="", encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            ts = int(row["open_time"])
            opens[ts] = float(row["open"])
            closes[ts] = float(row["close"])
    return opens, closes


def trades(symbol: str, opens: dict[int, float], closes: dict[int, float], delay_min: int,
           slip: float, fee: float, funding: float) -> list[dict]:
    threshold, hold, leverage = ((3.0, 6, 3.0) if symbol == "ETC" else (4.0, 12, 3.0))
    rows = core.read_candles(core.DATA_DIR / f"{symbol}USDT_1h.csv")
    t, c, r1, body, lower, upper, _ = indicators(rows)
    # 실행 시점에 알 수 있는 직전 24개 완료봉만 사용한다. indicators()의
    # centered convolution은 미래 거래량을 포함하므로 이 검증에는 사용할 수 없다.
    volumes = np.array([row["v"] for row in rows], dtype=float)
    vr = np.zeros(len(volumes), dtype=float)
    for j in range(24, len(volumes)):
        prior_mean = float(np.mean(volumes[j - 24:j]))
        vr[j] = volumes[j] / prior_mean if prior_mean > 0 else 0.0
    sig = pattern_signal("volume_shock_revert", r1, body, lower, upper, vr, threshold)
    out = []
    i = 24
    while i + 1 + hold < len(c):
        direction = int(sig[i])
        vol = float(np.std(r1[i - 24:i], ddof=1) * math.sqrt(365.25 * 24))
        if direction == 0 or abs(r1[i]) < .009 or vol > 1.5:
            i += 1
            continue
        base_entry_ts = int(t[i]) + 3_600_000
        entry_ts = base_entry_ts + delay_min * 60_000
        exit_ts = base_entry_ts + hold * 3_600_000 - FIVE_MIN
        entry, exit_price = opens.get(entry_ts), closes.get(exit_ts)
        if entry is None or exit_price is None:
            i += 1
            continue
        raw = direction * (exit_price / entry - 1) * leverage
        cost = 2 * (fee + slip) * leverage + (hold / 8) * funding * leverage
        out.append({"ts": exit_ts, "symbol": symbol, "ret": raw - cost})
        i += hold
    return out


def simulate(items: list[dict], start: int, end: int, scale: float = 1.75) -> dict:
    equity = peak = 1.0
    mdd = 0.0
    wins = 0
    yearly: dict[str, float] = {}
    for x in items[start:end]:
        weight = .9 if x["symbol"] == "ETC" else .1
        ret = scale * weight * x["ret"]
        equity *= max(0.0, 1 + ret)
        peak = max(peak, equity)
        mdd = min(mdd, equity / peak - 1)
        wins += ret > 0
        year = time.strftime("%Y", time.gmtime(x["ts"] / 1000))
        yearly[year] = (yearly.get(year, 1.0) * (1 + ret))
    count = end - start
    return {
        "multiple": equity, "return_pct": (equity - 1) * 100,
        "mdd_pct": mdd * 100, "trades": count,
        "win_rate_pct": wins / count * 100 if count else 0,
        "yearly_return_pct": {k: (v - 1) * 100 for k, v in yearly.items()},
    }


def main() -> None:
    paths = {s: download_5m(s) for s in SYMBOLS}
    px = {s: prices_5m(paths[s]) for s in SYMBOLS}
    scenarios = []
    for delay in (0, 5, 10, 15, 30):
        for cost, slip, fee, funding in (
            ("base", .0005, .0005, .0001),
            ("stress", .0010, .00075, .00015),
        ):
            items = []
            for symbol in SYMBOLS:
                items += trades(symbol, *px[symbol], delay, slip, fee, funding)
            items.sort(key=lambda x: x["ts"])
            n = len(items)
            cuts = (0, n // 3, 2 * n // 3, n)
            segments = [simulate(items, cuts[i], cuts[i + 1]) for i in range(3)]
            full = simulate(items, 0, n)
            passed = bool(
                full["return_pct"] > 1_000_000 and full["mdd_pct"] >= -50
                and all(x["return_pct"] > 0 and x["mdd_pct"] >= -50 and x["trades"] >= 20 for x in segments)
            )
            scenarios.append({"delay_min": delay, "cost": cost, "segments": segments, "full": full, "passed": passed})
    print(json.dumps({"method": "ETC90_LINK10_1H_VSR_5M_EXECUTION", "scenarios": scenarios}, ensure_ascii=False))


if __name__ == "__main__":
    main()

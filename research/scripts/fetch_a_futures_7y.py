"""Download the available Binance USD-M inputs for the seven-year A replay."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import fetch_full_futures_stage31 as fetcher


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/data_7y_futures"
SYMBOLS = ("BTC", "ETH", "XRP", "TRX", "SOL")


def main():
    start = int(datetime(2019, 8, 28, tzinfo=timezone.utc).timestamp() * 1000)
    end = int(datetime(2026, 8, 30, tzinfo=timezone.utc).timestamp() * 1000)
    fetcher.CACHE = OUT
    OUT.mkdir(parents=True, exist_ok=True)
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(fetcher.fetch_symbol, symbol, start, end): symbol for symbol in SYMBOLS}
        for job in as_completed(jobs):
            try:
                results.append(job.result())
            except Exception as exc:
                errors.append({"symbol": jobs[job], "error": str(exc)})
    coverage = {
        "source": "Binance USD-M public hourly klines and funding",
        "requested_range": ["2019-08-28", "2026-08-29"],
        "results": sorted(results, key=lambda row: row["symbol"]),
        "errors": errors,
    }
    (OUT / "COVERAGE.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    print(json.dumps(coverage, indent=2))
    if errors:
        raise SystemExit(1)


if __name__ == "__main__":
    main()

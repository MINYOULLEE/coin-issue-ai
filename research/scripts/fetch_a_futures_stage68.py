"""Download public Binance USD-M hourly and funding data for A Stage68 research."""
from __future__ import annotations

import hashlib
import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

from fetch_full_futures_stage31 import fetch_symbol


ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "research/results/a_exposure_scale_stage68"
SYMBOLS = ("BTC", "ETH", "XRP", "TRX", "SOL")


def main():
    start = int(datetime(2021, 8, 28, tzinfo=timezone.utc).timestamp() * 1000)
    end = int(datetime(2026, 8, 30, tzinfo=timezone.utc).timestamp() * 1000)
    # Reuse the downloader with a task-local cache instead of Stage31's B cache.
    import fetch_full_futures_stage31 as fetcher
    fetcher.CACHE = OUT / "data"
    fetcher.CACHE.mkdir(parents=True, exist_ok=True)
    results, errors = [], []
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(fetch_symbol, symbol, start, end): symbol for symbol in SYMBOLS}
        for job in as_completed(jobs):
            try:
                results.append(job.result())
            except Exception as error:
                errors.append({"symbol": jobs[job], "error": str(error)})
    coverage = {
        "source": "Binance USD-M public API",
        "start": start,
        "end": end,
        "results": sorted(results, key=lambda x: x["symbol"]),
        "errors": errors,
        "hashes": {
            str(path.relative_to(fetcher.CACHE)): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in fetcher.CACHE.glob("*/*.json") if path.name in ("hours.json", "funding.json")
        },
    }
    (OUT / "COVERAGE.json").write_text(json.dumps(coverage, indent=2), encoding="utf-8")
    print(json.dumps(coverage, indent=2))


if __name__ == "__main__":
    main()

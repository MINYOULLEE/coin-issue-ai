"""Research only: minute-delay and collision verification for Stage43 BNB candidate."""
import inspect
import json
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone

import research_b_combo_stage43 as s43


s40 = s43.s40
H, M = 3600000, 60000
OUT = s40.common.p.s.core.RESULT_DIR / "b_combo_stage44"
CACHE = OUT / "minute_windows"


def compact(x):
    return {k: v for k, v in x.items() if k != "ledger"}


def setup():
    candidate = json.loads((s40.common.p.s.core.RESULT_DIR / "b_combo_stage43/results.json").read_text(encoding="utf8"))["best"]
    series, core_entries, times, standard, ops = s40.build()
    weights = {"ALGO": 1.15, "ETH": 1.15, "VET": 1.15, "LINK": 1.15,
               "DOT": candidate["dot_request"], "LTC": 1.15}
    entries = s40.entries_for(core_entries, ops, weights)
    rows = s40.common.p.s.core.read_candles(s40.common.p.s.core.DATA_DIR / "BNBUSDT_1h.csv")
    for row in rows:
        row["symbol"] = "BNB"
    series["BNB"] = {r["t"]: r for r in rows}
    core_busy = set()
    for t, positions in core_entries.items():
        for position in positions:
            core_busy.update(range(t, position["exit_bar"] + H, H))
    signal = dict(s43.patterns.candidate_patterns(rows))["capitulation_n1_move0.03_vol3.0_wick0.25"]
    bnb_ops = s40.common.p.s.opportunities(rows, signal, 1, 3, core_busy)
    for op in bnb_ops:
        entries.setdefault(op["entry_ts"], []).append({**op, "weight_scale": candidate["bnb_request"] / 1.15})
    return candidate, series, entries, times, bnb_ops


def fetch(op):
    path = CACHE / f"BNB_{op['entry_ts']}.json"
    if path.exists():
        return {"cached": True}
    query = urllib.parse.urlencode({"symbol": "BNBUSDT", "interval": "1m", "startTime": op["entry_ts"],
                                    "endTime": op["entry_ts"] + 70 * M, "limit": 100})
    req = urllib.request.Request("https://api.binance.com/api/v3/klines?" + query,
                                 headers={"User-Agent": "coin-issue-research/1.0"})
    with urllib.request.urlopen(req, timeout=20) as response:
        rows = json.load(response)
    if len(rows) < 70 or any(int(row[0]) != op["entry_ts"] + i * M for i, row in enumerate(rows[:70])):
        raise RuntimeError("incomplete/gapped minute data")
    path.write_text(json.dumps(rows), encoding="utf8")
    return {"cached": False}


def main():
    OUT.mkdir(exist_ok=True)
    CACHE.mkdir(exist_ok=True)
    candidate, series, entries, times, bnb_ops = setup()
    unique = {x["entry_ts"]: x for x in bnb_ops if times[0] <= x["entry_ts"] <= times[-1]}
    fetched = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(fetch, op): ts for ts, op in unique.items()}
        for job in as_completed(jobs):
            try:
                fetched.append({"entry_ts": jobs[job], **job.result()})
            except Exception as exc:
                fetched.append({"entry_ts": jobs[job], "error": str(exc)})
    errors = [x for x in fetched if "error" in x]
    if errors:
        raise RuntimeError(f"minute fetch errors {len(errors)}: {errors[:3]}")

    minutes, mismatches = {}, []
    for ts in unique:
        rows = json.loads((CACHE / f"BNB_{ts}.json").read_text(encoding="utf8"))
        minute = {int(r[0]): {"o": float(r[1]), "h": float(r[2]), "l": float(r[3]), "c": float(r[4])} for r in rows}
        minutes[ts] = minute
        hour = series["BNB"][ts]
        checks = {"o": minute[ts]["o"], "c": minute[ts + 59*M]["c"],
                  "h": max(minute[ts + i*M]["h"] for i in range(60)),
                  "l": min(minute[ts + i*M]["l"] for i in range(60))}
        for field, value in checks.items():
            if abs(value - hour[field]) > max(1e-8, abs(hour[field]) * 1e-8):
                mismatches.append({"entry_ts": ts, "field": field, "hour": hour[field], "minute": value})
    if mismatches:
        raise RuntimeError(f"OHLC mismatch {len(mismatches)}")

    source = inspect.getsource(s40.common.p.s.b.replay)
    source = source.replace("target*(1+x", "target*x.get('weight_scale',1.)*(1+x")
    source = source.replace("margin = target*shrink", "margin = target*shrink*x.get('weight_scale',1.)")
    source = source.replace("raw_open = series[x['symbol']][t]['o']", "raw_open = entry_override.get((x['symbol'],t),series[x['symbol']][t]['o'])")
    source = source.replace("bar = series[s][t]", "bar = bar_override.get((s,t),series[s][t])")
    scenarios = []
    for delay in (0, 1, 3, 5, 10):
        prices, bars = {}, {}
        for ts in unique:
            v = minutes[ts]
            prices[("BNB", ts)] = v[ts + delay*M]["o"]
            bars[("BNB", ts)] = {"o": series["BNB"][ts]["o"], "c": v[ts + 59*M]["c"],
                                 "h": max(v[ts + i*M]["h"] for i in range(delay, 60)),
                                 "l": min(v[ts + i*M]["l"] for i in range(delay, 60))}
        env = {**s40.common.p.s.b.__dict__, "entry_override": prices, "bar_override": bars}
        exec(source, env)
        result = env["replay"](series, entries, times, 1.15)
        scenarios.append({"delay_minutes": delay, **compact(result)})

    bnb_intervals = [(x["entry_ts"], x["exit_bar"] + H) for x in bnb_ops]
    other = [x for rows in entries.values() for x in rows if x["symbol"] != "BNB"]
    collision = {
        "same_entry_boundary": sum(any(x["entry_ts"] == start for x in other) for start, _ in bnb_intervals),
        "holding_overlap_pairs": sum(start < x["exit_bar"] + H and end > x["entry_ts"] for start, end in bnb_intervals for x in other),
        "bnb_opportunities": len(bnb_intervals),
    }
    output = {"id": "B-COMBO-STAGE44", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "candidate": candidate, "minute_windows": len(unique),
              "ohlc_mismatches": mismatches, "entry_delay_scenarios": scenarios, "collision": collision,
              "passes_operating_ttl": all(x["return_pct"] > 1_000_000 and x["hourly_mark_mdd_pct"] >= -70
                                           and not x["liquidation_proxy_count"] for x in scenarios if x["delay_minutes"] < 5),
              "limitations": ["Binance spot minutes, not BingX futures fills", "Exit fixed at original hourly boundary",
                              "All historical data already used in discovery", "No live deployment"]}
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

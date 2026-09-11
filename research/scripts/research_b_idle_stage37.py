"""Research only: neighbourhood robustness for the residual-idle BNB reversal."""
import json
from datetime import datetime, timezone

import numpy as np

import research_b_idle_stage36 as p


OUT = p.s.core.RESULT_DIR / "b_idle_stage37"


def signal(rows, shock, volume, wick):
    o, h, l, c, v = [np.array([r[k] for r in rows]) for k in ("o", "h", "l", "c", "v")]
    ret = np.r_[0, c[1:] / c[:-1] - 1]
    span = np.maximum(h - l, 1e-12)
    lower = (np.minimum(o, c) - l) / span
    upper = (h - np.maximum(o, c)) / span
    avg48 = np.r_[np.full(48, np.nan), np.convolve(v, np.ones(48) / 48, "valid")[:-1]]
    return np.where((ret < -shock) & (v > avg48 * volume) & (lower > wick), 1,
                    np.where((ret > shock) & (v > avg48 * volume) & (upper > wick), -1, 0))


def main():
    OUT.mkdir(exist_ok=True)
    series, entries, times, standard = p.current_stage35()
    run = p.p.weighted_replay()
    base = run(series, entries, times, 1.15)
    stress_base = run(series, entries, times, 1.15, cost_mult=2)
    busy = set()
    for t, positions in entries.items():
        for position in positions:
            busy.update(range(t, position["exit_bar"] + 3600000, 3600000))
    rows = p.s.core.read_candles(p.s.core.DATA_DIR / "BNBUSDT_1h.csv")
    for row in rows:
        row["symbol"] = "BNB"
    series = {**series, "BNB": {r["t"]: r for r in rows}}
    cuts = [times[0] + int((times[-1] + 3600000 - times[0]) * k / 3) for k in range(4)]
    results = []
    for shock in (.02, .025, .03, .035, .04):
        for volume in (2, 2.5, 3, 3.5):
            for wick in (.15, .25, .35):
                raw = signal(rows, shock, volume, wick)
                np.testing.assert_array_equal(raw[:1200], signal(rows[:1200], shock, volume, wick))
                for leverage in (2, 3):
                    ops = p.s.opportunities(rows, raw, 1, leverage, busy)
                    for fraction in (.1, .15, .2, .25, .3):
                        ee = {t: [dict(x) for x in positions] for t, positions in entries.items()}
                        for op in ops:
                            ee.setdefault(op["entry_ts"], []).append({**op, "weight_scale": fraction / 1.15})
                        full = run(series, ee, times, 1.15)
                        stress = run(series, ee, times, 1.15, cost_mult=2)
                        segments = [p.p.compact(run(series, ee, times, 1.15, start=cuts[k], end=cuts[k + 1])) for k in range(3)]
                        passed = (len(ops) >= 12 and all(x["return_pct"] > 0 for x in segments)
                                  and full["return_pct"] > base["return_pct"]
                                  and stress["return_pct"] > stress_base["return_pct"]
                                  and full["hourly_mark_mdd_pct"] >= -70
                                  and not full["liquidation_proxy_count"] and not stress["liquidation_proxy_count"])
                        results.append({"shock": shock, "volume": volume, "wick": wick,
                                        "leverage": leverage, "target_fraction": fraction,
                                        "extra_trades": len(ops), "full": p.p.compact(full),
                                        "double_cost": p.p.compact(stress), "segments": segments,
                                        "pass": passed})
    results.sort(key=lambda x: (x["pass"], x["full"]["return_pct"]), reverse=True)
    passed = [x for x in results if x["pass"]]
    output = {"id": "B-IDLE-STAGE37", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "baseline": p.p.compact(base),
              "baseline_double_cost": p.p.compact(stress_base), "tested": len(results),
              "passed": len(passed), "best": results[0], "top_passed": passed[:25],
              "limitations": ["Neighbourhood search uses the same three historical partitions", "Hourly Binance spot proxy", "No live deployment"]}
    (OUT / "results.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps({k: output[k] for k in ("tested", "passed", "best")}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

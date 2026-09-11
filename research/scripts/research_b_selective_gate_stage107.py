"""Search selective causal risk gates that improve return and drawdown together."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import optimize_b_delay_stage101 as s101
import repair_b_7y_stage97 as s97


ab = s101.ab
OUT = ab.OUT / "B_STAGE107_SELECTIVE_GATE_SEARCH.json"
BASE = {"five_return": 4_827_595.900968802, "seven_return": 11_812_856.599994808,
        "five_mdd": -50.860954241435685, "seven_mdd": -62.78565676276365}
CORE = {"BCH", "LINK", "UNI"}


def compact(x):
    return {k: v for k, v in x.items() if k != "ledger"}


def main():
    series, entries, times, _ = s101.delayed_inputs(1)
    symbols = sorted({r["symbol"] for rows in entries.values() for r in rows})
    btc = {r["t"]: r for r in ab.core.read_candles(ab.SPOT / "BTCUSDT_1h.csv")}
    features = {s: ab.b91.s90.s86.s58.old.prev.features(list(rows.values()))
                for s, rows in series.items()}
    screens = []
    scopes = [("core", CORE)] + [(f"core_plus_{s}", CORE | {s}) for s in symbols if s not in CORE]
    for label, scope in scopes:
        for lookback in (12, 24, 48, 72):
            for threshold in (-.04, -.05, -.06, -.07):
                filtered, blocked = {}, 0
                for stamp, rows in entries.items():
                    recent, prior = btc.get(stamp-s97.HOUR), btc.get(stamp-(lookback+1)*s97.HOUR)
                    ret = recent["c"]/prior["c"]-1 if recent and prior else None
                    kept = []
                    for row in rows:
                        if row["symbol"] in scope and ret is not None and ret <= threshold:
                            blocked += 1
                        else:
                            kept.append(dict(row))
                    filtered[stamp] = kept
                exits = s101.s99.learned_exits(series, filtered, features)
                fn = s97.runner(exits, 3.75, .25, 168)
                seven = fn(series, filtered, times, 1.15)
                five = fn(series, filtered, times, 1.15, start=s101.START_5Y, end=s101.END)
                screens.append({"scope": label, "blocked_symbols": sorted(scope),
                    "lookback_hours": lookback, "threshold_pct": threshold*100,
                    "blocked": blocked, "seven_year": compact(seven), "five_year": compact(five),
                    "return_not_lower": seven["return_pct"] >= BASE["seven_return"] and five["return_pct"] >= BASE["five_return"],
                    "mdd_better": seven["hourly_mark_mdd_pct"] > BASE["seven_mdd"] and five["hourly_mark_mdd_pct"] > BASE["five_mdd"]})
    passing = [x for x in screens if x["return_not_lower"] and x["mdd_better"]
               and x["seven_year"]["hourly_adverse_bound_pct"] >= -70
               and x["five_year"]["hourly_adverse_bound_pct"] >= -70]
    result = {"id": "B-STAGE107-SELECTIVE-CAUSAL-GATE", "generated_at": datetime.now(timezone.utc).isoformat(),
              "research_only": True, "live_changes": False, "baseline": BASE,
              "screen_count": len(screens), "passing": passing,
              "top_by_joint_mdd": sorted(screens, key=lambda x: min(x["seven_year"]["hourly_mark_mdd_pct"]-BASE["seven_mdd"], x["five_year"]["hourly_mark_mdd_pct"]-BASE["five_mdd"]), reverse=True)[:10],
              "limitations": ["Parameters were searched on observed history; passing candidates need fixed delay, cost, and split validation.", "Only completed BTC candles are used.", "No live settings changed."]}
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"screen_count": len(screens), "passing": passing}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

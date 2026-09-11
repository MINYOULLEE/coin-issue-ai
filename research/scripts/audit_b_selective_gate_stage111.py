"""Causality and reproducibility audit for the fixed Stage108 research candidate."""
from __future__ import annotations

import json
from collections import Counter
from datetime import datetime, timezone

import optimize_b_delay_stage101 as s101
import repair_b_7y_stage97 as s97
import validate_b_selective_gate_stage108 as s108

ab = s101.ab
OUT = ab.OUT / "B_STAGE111_CAUSALITY_REPRODUCIBILITY_AUDIT.json"


def compact(x): return {k: v for k, v in x.items() if k != "ledger"}


def main():
    series, entries, times, _ = s101.delayed_inputs(1)
    btc = {r["t"]: r for r in ab.core.read_candles(ab.SPOT / "BTCUSDT_1h.csv")}
    filtered, blocked_count = s108.filter_entries(entries, -.06)
    missing, blocked, eligible = [], [], 0
    for stamp, rows in entries.items():
        recent_ts, prior_ts = stamp-s97.HOUR, stamp-73*s97.HOUR
        assert prior_ts < recent_ts < stamp
        recent, prior = btc.get(recent_ts), btc.get(prior_ts)
        for row in rows:
            if row["symbol"] not in s108.SCOPE: continue
            eligible += 1
            if recent is None or prior is None:
                missing.append({"symbol":row["symbol"],"entry_ts":stamp})
                continue
            ret = recent["c"]/prior["c"]-1
            if ret <= -.06:
                blocked.append({"symbol":row["symbol"],"entry_ts":stamp,"recent_ts":recent_ts,
                                "prior_ts":prior_ts,"btc_72h_return":ret})
    assert len(blocked) == blocked_count
    # Rebuild all adaptive exits and verify every learned sample was known by entry time.
    features = {s: ab.b91.s90.s86.s58.old.prev.features(list(rows.values())) for s, rows in series.items()}
    exits = {}
    causal_decisions = []
    for symbol, (quantile, keep, conditional) in ab.b91.s90.s86.CHOICES.items():
        learned, decisions = ab.b91.s90.s86.s61.learned_profit_locks(
            series, filtered, features, symbol.lower(), quantile, keep, conditional)
        exits.update(learned); causal_decisions.extend(decisions)
    violations = [d for d in causal_decisions if d.get("latest_training_close") is not None
                  and d["latest_training_close"] > d["entry_ts"]]
    assert not violations
    fn = s97.runner(exits, 3.75, .25, 168)
    seven = fn(series, filtered, times, 1.15)
    five = fn(series, filtered, times, 1.15, start=s101.START_5Y, end=s101.END)
    expected = json.loads((ab.OUT/"B_STAGE108_SELECTIVE_GATE_VALIDATION.json").read_text(encoding="utf-8"))
    one = next(c for c in expected["candidates"] if c["btc_72h_threshold_pct"] == -6)["scenarios"]
    saved = next(x for x in one if x["delay_minutes"] == 1)
    checks = {
        "five_return_exact": abs(five["return_pct"]-saved["five"]["return_pct"]) < 1e-8,
        "five_mdd_exact": abs(five["hourly_mark_mdd_pct"]-saved["five"]["hourly_mark_mdd_pct"]) < 1e-10,
        "seven_return_exact": abs(seven["return_pct"]-saved["seven"]["return_pct"]) < 1e-8,
        "seven_mdd_exact": abs(seven["hourly_mark_mdd_pct"]-saved["seven"]["hourly_mark_mdd_pct"]) < 1e-10,
    }
    assert all(checks.values())
    result = {"id":"B-STAGE111-CAUSALITY-REPRODUCIBILITY-AUDIT",
              "generated_at":datetime.now(timezone.utc).isoformat(),"research_only":True,"live_changes":False,
              "candidate":{"gross_cap":3.75,"drawdown_trigger_pct":25,"cooldown_hours":168,
                           "btc_lookback_completed_hours":72,"btc_threshold_pct":-6,
                           "blocked_symbols":sorted(s108.SCOPE)},
              "causality":{"eligible_entries":eligible,"blocked_entries":len(blocked),
                           "missing_btc_history_entries":len(missing),"future_training_violations":len(violations),
                           "blocked_by_symbol":dict(Counter(x["symbol"] for x in blocked))},
              "reproduction":checks,"five_year":compact(five),"extended":compact(seven),
              "live_requirements":["Use only the close of the candle ending one hour before entry and the close 72 hours before it.",
                                   "Block only new BCH/ICP/LINK/UNI proposals; never block exits or other symbols.",
                                   "Persist account equity peak and pause_until across invocations.",
                                   "On missing/stale BTC history, fail closed for protected-symbol new entries and alert diagnostics.",
                                   "Preserve order preflight, reserved margin, fixed entry quantity, and A/B account isolation."],
              "limitations":["Exact reproduction is historical, not independent future validation.",
                             "Actual BingX slippage and future regime remain unknown."]}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__ == "__main__": main()

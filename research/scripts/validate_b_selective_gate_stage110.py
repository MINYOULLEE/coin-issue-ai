"""Compare fixed Stage108 gate with its Stage105 baseline on rolling 12-month windows."""
from __future__ import annotations

import json
from datetime import datetime, timezone

import optimize_b_delay_stage101 as s101
import repair_b_7y_stage97 as s97
import validate_b_selective_gate_stage108 as s108

ab = s101.ab
OUT = ab.OUT / "B_STAGE110_ROLLING_BASELINE_COMPARISON.json"
SIX_MONTHS = 182 * 24 * s97.HOUR
YEAR = 365 * 24 * s97.HOUR


def compact(x): return {k: v for k, v in x.items() if k != "ledger"}


def main():
    series, raw_entries, times, _ = s101.delayed_inputs(1)
    gated_entries, blocked = s108.filter_entries(raw_entries, -.06)
    features = {s: ab.b91.s90.s86.s58.old.prev.features(list(rows.values())) for s, rows in series.items()}
    baseline_exits = s101.s99.learned_exits(series, raw_entries, features)
    gated_exits = s101.s99.learned_exits(series, gated_entries, features)
    baseline = s97.runner(baseline_exits, 3.75, .25, 168)
    candidate = s97.runner(gated_exits, 3.75, .25, 168)
    start, final = min(times), max(times) + s97.HOUR
    windows = []
    cursor = start
    while cursor + YEAR <= final:
        row = {"start": datetime.fromtimestamp(cursor/1000, timezone.utc).isoformat(),
               "end": datetime.fromtimestamp((cursor+YEAR)/1000, timezone.utc).isoformat()}
        for label, fn, entries in (("baseline", baseline, raw_entries), ("candidate", candidate, gated_entries)):
            row[label] = compact(fn(series, entries, times, 1.15, start=cursor, end=cursor+YEAR))
            row[label+"_double_cost"] = compact(fn(series, entries, times, 1.15, cost_mult=2, start=cursor, end=cursor+YEAR))
        row["candidate_return_better"] = row["candidate"]["return_pct"] >= row["baseline"]["return_pct"]
        row["candidate_mdd_better"] = row["candidate"]["hourly_mark_mdd_pct"] >= row["baseline"]["hourly_mark_mdd_pct"]
        row["candidate_double_cost_better"] = row["candidate_double_cost"]["return_pct"] >= row["baseline_double_cost"]["return_pct"]
        windows.append(row)
        cursor += SIX_MONTHS
    # Explicitly compare the partial 2026 interval that failed Stage109 double-cost profitability.
    y2026 = int(datetime(2026,1,1,tzinfo=timezone.utc).timestamp()*1000)
    partial = {}
    for label, fn, entries in (("baseline", baseline, raw_entries), ("candidate", candidate, gated_entries)):
        partial[label] = compact(fn(series, entries, times, 1.15, start=y2026, end=final))
        partial[label+"_double_cost"] = compact(fn(series, entries, times, 1.15, cost_mult=2, start=y2026, end=final))
    result = {"id":"B-STAGE110-ROLLING-BASELINE-COMPARISON",
              "generated_at":datetime.now(timezone.utc).isoformat(),"research_only":True,"live_changes":False,
              "candidate":{"btc_completed_72h_return_lte_pct":-6,"block_new_entries_only":sorted(s108.SCOPE),"blocked_signals":blocked},
              "rolling_12m_step_6m":windows,
              "counts":{"windows":len(windows),
                        "return_better":sum(x["candidate_return_better"] for x in windows),
                        "mdd_better":sum(x["candidate_mdd_better"] for x in windows),
                        "double_cost_return_better":sum(x["candidate_double_cost_better"] for x in windows),
                        "candidate_profitable":sum(x["candidate"]["end_usd"]>100 for x in windows),
                        "candidate_double_cost_profitable":sum(x["candidate_double_cost"]["end_usd"]>100 for x in windows)},
              "partial_2026":partial,
              "limitations":["All windows reuse historical data and overlap by six months.","This is comparative robustness, not untouched future validation.","No live settings changed."]}
    OUT.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(result,ensure_ascii=False),flush=True)


if __name__ == "__main__": main()

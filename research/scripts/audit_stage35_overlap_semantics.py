"""Compare adopted research selection gates with the deployed Stage35 opportunity semantics."""
import json
from collections import Counter

import research_b_allocation_stage39 as stage
import research_b_idle_stage36 as common


def intervals(entries):
    out = []
    for positions in entries.values():
        for p in positions:
            out.append((p["entry_ts"], p["exit_bar"] + 3600000, p["symbol"]))
    return out


def main():
    series, core_entries, times = common.p.s.b.prepare()
    standard = json.loads((common.p.ROOT / "strategy/plan_b_combination_standard.json").read_text(encoding="utf8"))
    selectors = standard["reference"]["selector"]["patterns"]
    core_busy = set()
    for start, end, _ in intervals(core_entries):
        core_busy.update(range(start, end, 3600000))
    research_ops = {}
    runtime_ops = {}
    old_busy = set(core_busy)
    for index, ident in enumerate(selectors):
        symbol, pattern, _ = ident.split(":")
        rows = common.p.s.core.read_candles(common.p.s.core.DATA_DIR / f"{symbol}USDT_1h.csv")
        for row in rows:
            row["symbol"] = symbol
        series[symbol] = {row["t"]: row for row in rows}
        signal = dict(common.p.candidate_patterns(rows))[pattern]
        leverage = int(standard["symbols"][symbol]["leverage"])
        # Deployed state tracks coreBusyUntil and per-symbol cooldown, but not supplementBusyUntil.
        runtime_ops[symbol] = common.p.s.opportunities(rows, signal, 1, leverage, core_busy)
        gate = core_busy if index < 3 else old_busy
        research_ops[symbol] = common.p.s.opportunities(rows, signal, 1, leverage, gate)
        if index < 3:
            for op in research_ops[symbol]:
                old_busy.update(range(op["entry_ts"], op["exit_bar"] + 3600000, 3600000))
    extra = []
    missing = []
    for symbol in ("LINK", "DOT", "LTC"):
        kept = {x["entry_ts"] for x in research_ops[symbol]}
        emitted = {x["entry_ts"] for x in runtime_ops[symbol]}
        extra.extend({"symbol": symbol, "entry_ts": x["entry_ts"]} for x in runtime_ops[symbol] if x["entry_ts"] not in kept)
        missing.extend({"symbol": symbol, "entry_ts": x["entry_ts"]} for x in research_ops[symbol] if x["entry_ts"] not in emitted)
    # Count cross-symbol supplement holding overlaps under deployed semantics.
    all_runtime = [x for values in runtime_ops.values() for x in values]
    entry_counts = Counter(x["entry_ts"] for x in all_runtime)
    multi_entry_hours = {t: count for t, count in entry_counts.items() if count > 1}
    overlaps = []
    for i, a in enumerate(all_runtime):
        for b in all_runtime[i + 1:]:
            if a["symbol"] == b["symbol"]:
                continue
            a_end = a["exit_bar"] + 3600000
            b_end = b["exit_bar"] + 3600000
            if a["entry_ts"] < b_end and b["entry_ts"] < a_end:
                overlaps.append(tuple(sorted((a["symbol"], b["symbol"]))))
    research_total = sum(len(x) for x in research_ops.values())
    runtime_total = sum(len(x) for x in runtime_ops.values())
    run = common.p.weighted_replay()
    cuts = [times[0] + int((times[-1] + 3600000 - times[0]) * k / 3) for k in range(4)]
    def replay_weights(weights):
        ee = {t: [dict(x) for x in positions] for t, positions in core_entries.items()}
        for symbol, ops in runtime_ops.items():
            for op in ops:
                ee.setdefault(op["entry_ts"], []).append({**op, "weight_scale": weights[symbol] / 1.15})
        full = run(series, ee, times, 1.15)
        stress = run(series, ee, times, 1.15, cost_mult=2)
        segments = [common.p.compact(run(series, ee, times, 1.15, start=cuts[k], end=cuts[k + 1])) for k in range(3)]
        return {"full": common.p.compact(full), "double_cost": common.p.compact(stress), "segments": segments}
    current_weights = {symbol: float(standard["symbols"][symbol]["target_margin_fraction"]) for symbol in runtime_ops}
    stage39_weights = {"ALGO": 1.15, "ETH": 1.15, "VET": 1.15, "LINK": 1.15, "DOT": .6, "LTC": 1.15}
    output = {
        "research_opportunities": {k: len(v) for k, v in research_ops.items()},
        "deployed_semantics_opportunities": {k: len(v) for k, v in runtime_ops.items()},
        "research_total": research_total,
        "deployed_semantics_total": runtime_total,
        "unmodelled_new_supplement_opportunities": len(extra),
        "unmodelled_rate_vs_research_pct": 100 * len(extra) / research_total,
        "unmodelled_by_symbol": dict(Counter(x["symbol"] for x in extra)),
        "researched_but_shifted_out_by_runtime_cooldown": len(missing),
        "shifted_out_by_symbol": dict(Counter(x["symbol"] for x in missing)),
        "cross_symbol_holding_overlap_pairs": len(overlaps),
        "distinct_supplement_entry_hours": len(entry_counts),
        "multi_supplement_entry_hours": len(multi_entry_hours),
        "multi_entry_hour_rate_pct": 100 * len(multi_entry_hours) / len(entry_counts),
        "opportunities_in_multi_entry_hours": sum(multi_entry_hours.values()),
        "opportunity_overlap_rate_pct": 100 * sum(multi_entry_hours.values()) / len(all_runtime),
        "overlap_pair_counts": {" + ".join(k): v for k, v in Counter(overlaps).most_common()},
        "deployed_semantics_stage35_replay": replay_weights(current_weights),
        "deployed_semantics_stage39_replay": replay_weights(stage39_weights),
        "verdict": "research/runtime selection mismatch" if extra else "match",
    }
    path = common.p.s.core.RESULT_DIR / "b_allocation_stage39" / "overlap_audit.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf8")
    print(json.dumps(output, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    main()

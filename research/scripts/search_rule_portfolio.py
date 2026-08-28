from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone

import numpy as np

import replay_mdd30 as core
import repair_coin_strategy as repair
import search_rule_strategies as rules


def target_series(symbol: str, candidate: dict):
    items = repair.build_dataset(symbol)
    times = np.array([z[0] for z in items], dtype=np.int64)
    x = np.array([z[1] for z in items], dtype=float)
    realized = np.array([z[3] for z in items], dtype=float)
    raw = rules.signal_for(x, candidate["family"], candidate["a"], candidate["b"])
    if candidate["side"] == "long": raw[raw < 0] = 0
    if candidate["side"] == "short": raw[raw > 0] = 0
    vol = np.ones(len(raw))
    if candidate["vol_target"]:
        vol = np.clip(candidate["vol_target"] / np.maximum(x[:, rules.IDX["vol_72"]], .05), .25, 1.5)
    target = np.zeros(len(raw)); equity = 1.; peak = 1.; guarded = False; previous = 0.
    pnl = np.zeros(len(raw)); turnover = np.zeros(len(raw))
    for i in range(len(raw)):
        dd = equity / peak - 1
        if candidate["drawdown_guard"] and dd <= -.20: guarded = True
        if candidate["drawdown_guard"] and guarded and dd >= -.05: guarded = False
        target[i] = raw[i] * candidate["exposure"] * vol[i] * (.5 if guarded else 1.)
        turnover[i] = abs(target[i] - previous)
        pnl[i] = target[i] * realized[i] - turnover[i] * .0005
        equity *= max(0., 1 + pnl[i]); peak = max(peak, equity); previous = target[i]
    return {int(t): (float(p), float(to)) for t, p, to in zip(times, pnl, turnover)}


def simulate(times, pnl_matrix, indices, scale):
    daily = pnl_matrix[:, indices].mean(axis=1) * scale
    equity = 1.; peak = 1.; mdd = 0.; year_start = {}; year_end = {}
    for stamp, ret in zip(times, daily):
        year = str(datetime.fromtimestamp(int(stamp) / 1000, timezone.utc).year)
        year_start.setdefault(year, equity)
        equity *= max(0., 1 + ret); peak = max(peak, equity); mdd = min(mdd, equity / peak - 1); year_end[year] = equity
    yearly = {y: float((year_end[y] / year_start[y] - 1) * 100) if year_start[y] else -100.0 for y in year_end}
    return {"multiple": float(equity), "return_pct": float((equity - 1) * 100), "mdd_pct": float(mdd * 100), "yearly_return_pct": yearly, "positive_years": int(sum(v > 0 for v in yearly.values()))}


def main():
    files = sorted(core.RESULT_DIR.glob("*_rule_search.json"))
    selected = {}
    for path in files:
        report = json.loads(path.read_text(encoding="utf-8"))
        selected[report["symbol"]] = report["train_selected_best"]
    streams = {symbol: target_series(symbol, candidate) for symbol, candidate in selected.items()}
    common = sorted(set.intersection(*(set(z) for z in streams.values())))
    symbols = sorted(streams)
    pnl = np.array([[streams[s][t][0] for s in symbols] for t in common], dtype=float)
    times = np.array(common, dtype=np.int64); split = int(len(times) * .70)
    search = []
    for size in (2, 3, 4, 5):
        for indices in itertools.combinations(range(len(symbols)), size):
            for scale in (.5, 1., 1.5, 2., 2.5, 3.):
                train = simulate(times[:split], pnl[:split], indices, scale)
                score = np.log(max(train["multiple"], 1e-12)) + train["mdd_pct"] / 30 + train["positive_years"] * .2
                if train["mdd_pct"] < -55 or train["positive_years"] < len(train["yearly_return_pct"]) - 1: score -= 10
                search.append({"score": float(score), "symbols": [symbols[i] for i in indices], "scale": scale, "train": train})
    # Hard-filter risk before touching the independent period. High-return
    # portfolios that already violate the MDD gate must not crowd out safer ones.
    search = [z for z in search if z["train"]["mdd_pct"] >= -50 and z["train"]["positive_years"] >= len(z["train"]["yearly_return_pct"]) - 1]
    search.sort(key=lambda z: z["score"], reverse=True)
    evaluated = []
    for row in search[:300]:
        indices = [symbols.index(s) for s in row["symbols"]]
        test = simulate(times[split:], pnl[split:], indices, row["scale"])
        full = simulate(times, pnl, indices, row["scale"])
        gate = bool(full["return_pct"] >= 10_000 and full["mdd_pct"] >= -50 and test["return_pct"] > 0 and test["mdd_pct"] >= -50)
        evaluated.append({**row, "test": test, "full": full, "gate_10000": gate})
    passing = [z for z in evaluated if z["gate_10000"]]
    output = {"generated_at": datetime.now(timezone.utc).isoformat(), "symbols_screened": symbols, "gate": "five-year >=10000%; MDD <=50%; independent final 30% positive and MDD <=50%", "passing_count": len(passing), "best_passing": max(passing, key=lambda z: z["full"]["return_pct"]) if passing else None, "train_selected_best": evaluated[0], "top_100": evaluated}
    (core.RESULT_DIR / "rule_portfolio_search.json").write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()

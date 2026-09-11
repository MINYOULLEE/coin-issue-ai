from __future__ import annotations

import json
from datetime import datetime, timezone

import numpy as np

import replay_mdd30 as core
import combine_novel_patterns as combo


SYMBOLS = ("AVAX", "ICP", "BCH", "DOGE", "UNI")
BASE_LEVERAGE = np.array([3.0, 5.0, 3.0, 5.0, 2.0])
MAX_GROSS = 10.0
RANDOM_SEED = 20260830
SAMPLES = 120_000


def simulate(matrix: np.ndarray, weights: np.ndarray, start: int, end: int, cost_stress: float = 1.0) -> dict:
    # Each stream already includes standard costs. A stress above 1 subtracts
    # the incremental standard round-trip cost estimate from every active leg.
    block = matrix[start:end]
    active = block != 0
    extra = (cost_stress - 1.0) * 0.0015 * BASE_LEVERAGE
    pnl = ((block - active * extra) * weights).sum(axis=1)
    used = active.any(axis=1); pnl = pnl[used]
    if not len(pnl):
        return {"multiple": 1.0, "return_pct": 0.0, "mdd_pct": 0.0, "event_count": 0}
    curve = np.cumprod(np.maximum(0.0, 1 + pnl)); peaks = np.maximum.accumulate(np.r_[1.0, curve])[1:]
    mdd = float(np.min(curve / peaks - 1)); multiple = float(curve[-1])
    return {"multiple": multiple, "return_pct": (multiple - 1) * 100, "mdd_pct": mdd * 100,
            "event_count": int(len(pnl)), "positive_event_rate_pct": float(np.mean(pnl > 0) * 100)}


def main() -> None:
    source = json.loads((core.RESULT_DIR / "novel_pattern_search_stage10.json").read_text(encoding="utf-8"))
    best = {x["best"]["symbol"]: x["best"] for x in source["results"] if x["best"]}
    streams = {s: combo.trade_stream(best[s]) for s in SYMBOLS}
    times = sorted(set().union(*(set(v) for v in streams.values())))
    matrix = np.array([[streams[s].get(t, 0.0) for s in SYMBOLS] for t in times], dtype=float)
    cuts = (0, len(times) // 3, 2 * len(times) // 3, len(times))

    rng = np.random.default_rng(RANDOM_SEED)
    raw = rng.dirichlet(np.ones(len(SYMBOLS)), size=SAMPLES)
    gross_targets = rng.uniform(4.0, MAX_GROSS, size=SAMPLES)
    weights = raw * gross_targets[:, None] / (raw * BASE_LEVERAGE).sum(axis=1)[:, None]
    # Include interpretable equal-risk anchors.
    anchors = []
    for gross in (4., 5., 6., 7., 8., 9., 10.):
        anchors.append(np.repeat(gross / BASE_LEVERAGE.sum(), len(SYMBOLS)))
    weights = np.vstack([weights, np.array(anchors)])

    shortlist = []
    # Cheap vector-free evaluation is acceptable here because only five legs and sparse events.
    for w in weights:
        seg = [simulate(matrix, w, cuts[k], cuts[k + 1]) for k in range(3)]
        if not all(x["return_pct"] > 0 and x["mdd_pct"] >= -50 for x in seg): continue
        full = simulate(matrix, w, 0, len(times))
        score = min(np.log(max(x["multiple"], 1e-12)) for x in seg) + np.log(max(full["multiple"], 1e-12)) / 4
        shortlist.append((float(score), w.copy(), seg, full))
    shortlist.sort(key=lambda x: x[0], reverse=True)

    evaluated = []
    for score, w, seg, full in shortlist[:200]:
        stress = simulate(matrix, w, 0, len(times), 2.0)
        gross = float(np.dot(w, BASE_LEVERAGE))
        passed = bool(full["return_pct"] >= 1_000_000 and full["mdd_pct"] >= -50 and stress["return_pct"] > 0 and stress["mdd_pct"] >= -50)
        evaluated.append({"score": score, "weights": dict(zip(SYMBOLS, map(float, w))), "gross_exposure": gross,
                          "segments": seg, "full": full, "double_cost_stress": stress, "passed": passed})
    passing = [x for x in evaluated if x["passed"]]
    out = {"generated_at": datetime.now(timezone.utc).isoformat(), "seed": RANDOM_SEED, "random_samples": SAMPLES,
           "symbols": SYMBOLS, "base_leverage": dict(zip(SYMBOLS, map(float, BASE_LEVERAGE))), "max_gross": MAX_GROSS,
           "survivors": len(shortlist), "passing_count": len(passing), "best": evaluated[0],
           "best_passing": max(passing, key=lambda x: x["full"]["return_pct"]) if passing else None, "top_200": evaluated}
    path = core.RESULT_DIR / "novel_pattern_risk_optimization_stage12.json"
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"saved": str(path), "survivors": len(shortlist), "passing": len(passing),
                      "best": evaluated[0], "best_passing": out["best_passing"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__": main()

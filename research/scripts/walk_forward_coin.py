from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone

import numpy as np
from sklearn.tree import DecisionTreeClassifier

import train_coin_answer as base
import replay_mdd30 as core


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("symbol", nargs="?", default="BNB")
    symbol = parser.parse_args().symbol.upper()
    _, items = base.dataset(symbol)
    times = np.array([z[0] for z in items], dtype=np.int64)
    x = np.array([z[1] for z in items], dtype=float)
    future = np.array([z[2] for z in items], dtype=float)
    n = len(x)
    boundaries = [int(n * p) for p in (.40, .55, .70, .85)]
    folds = [(0, boundaries[0], boundaries[1]), (0, boundaries[1], boundaries[2]), (0, boundaries[2], boundaries[3])]
    holdout_start = boundaries[3]
    records = []
    exposure_sets = ((0., .25, .5), (0., .5, 1.), (.1, .5, 1.), (0., 1., 1.5), (.25, 1., 1.5))
    for neutral in (.001, .002, .003, .005, .0075, .01):
        y = base.classify(future, neutral)
        for depth in range(3, 9):
            for leaf in (2, 5, 10, 20):
                predictions = []
                for start, train_end, validation_end in folds:
                    model = DecisionTreeClassifier(max_depth=depth, min_samples_leaf=leaf, class_weight="balanced", random_state=42).fit(x[start:train_end], y[start:train_end])
                    predictions.append(base.probabilities(model, x[train_end:validation_end]))
                for low, high in ((.45, .60), (.50, .65), (.55, .70), (.55, .75), (.60, .75)):
                    for exposure in exposure_sets:
                        results = []
                        for (_, train_end, validation_end), (direction, confidence) in zip(folds, predictions):
                            results.append(base.simulate(times[train_end:validation_end], future[train_end:validation_end], direction, confidence, low, high, exposure))
                        multiples = [z["multiple"] for z in results]
                        worst_mdd = min(z["mdd_pct"] for z in results)
                        score = sum(np.log(max(z, 1e-9)) for z in multiples) / len(multiples) + worst_mdd / 25 - depth * .01
                        if min(multiples) <= .90 or worst_mdd < -35:
                            score -= 10
                        records.append({"score": float(score), "neutral": neutral, "depth": depth, "min_samples_leaf": leaf, "low": low, "high": high, "exposures": exposure, "folds": results, "worst_fold_multiple": min(multiples), "worst_fold_mdd_pct": worst_mdd})
    records.sort(key=lambda z: z["score"], reverse=True)
    selected = records[0]
    y = base.classify(future, selected["neutral"])
    model = DecisionTreeClassifier(max_depth=selected["depth"], min_samples_leaf=selected["min_samples_leaf"], class_weight="balanced", random_state=42).fit(x[:holdout_start], y[:holdout_start])
    direction, confidence = base.probabilities(model, x[holdout_start:])
    holdout = base.simulate(times[holdout_start:], future[holdout_start:], direction, confidence, selected["low"], selected["high"], selected["exposures"])
    output = {
        "symbol": symbol, "generated_at": datetime.now(timezone.utc).isoformat(), "samples": n,
        "fold_boundaries": boundaries, "selected": selected,
        "holdout_range": [datetime.fromtimestamp(times[holdout_start] / 1000, timezone.utc).isoformat(), datetime.fromtimestamp(times[-1] / 1000, timezone.utc).isoformat()],
        "holdout": holdout, "tree": {"nodes": int(model.tree_.node_count), "depth": int(model.tree_.max_depth), "leaves": int(model.tree_.n_leaves)},
        "promotion_gate": bool(holdout["multiple"] > 1 and holdout["mdd_pct"] >= -30 and selected["worst_fold_multiple"] > .9 and selected["worst_fold_mdd_pct"] >= -35),
        "top_20": records[:20],
    }
    core.RESULT_DIR.mkdir(parents=True, exist_ok=True)
    path = core.RESULT_DIR / f"{symbol.lower()}_walk_forward.json"
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
